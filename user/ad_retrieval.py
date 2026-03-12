"""
Enhanced Ad Retrieval System with Query Prioritization
Features: Two-Step Hybrid Retrieval + Query Repetition for Emphasis
STORAGE: Pinecone Vector Database (metadata stored in Pinecone, no local files)
EMBEDDINGS: HuggingFace Inference API (Free Tier)
KEYWORDS: TF-IDF based extraction (no model downloads)

IMPROVEMENTS:
- No KeyBERT dependency (using TF-IDF for keyword extraction)
- All metadata stored in Pinecone (no local .pkl files)
- Direct ad_id usage (no faiss_id intermediate mapping)
- Robust error handling and retry logic
- Production-ready logging
- Native Pinecone client only (no langchain_pinecone / langchain_core)
"""

from langchain_huggingface import HuggingFaceEndpointEmbeddings
from pinecone import Pinecone, ServerlessSpec  
from sklearn.feature_extraction.text import TfidfVectorizer
from dataclasses import dataclass, field
import numpy as np
import os
import time
from typing import List, Dict, Optional, Set
from django.conf import settings
import threading
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# LIGHTWEIGHT DOCUMENT REPLACEMENT
# ============================================================================

@dataclass
class AdDocument:
    """Drop-in replacement for langchain_core.documents.Document"""
    page_content: str
    metadata: Dict = field(default_factory=dict)


# ============================================================================
# CONFIGURATION
# ============================================================================

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
HUGGINGFACE_API_KEY = getattr(settings, 'HUGGINGFACE_API_TOKEN', os.getenv('HUGGINGFACE_API_TOKEN'))
PINECONE_API_KEY = getattr(settings, 'PINECONE_API_KEY', os.getenv('PINECONE_API_KEY'))
PINECONE_INDEX_NAME = getattr(settings, 'PINECONE_INDEX_NAME', 'ad-retrieval-index')
PINECONE_ENVIRONMENT = getattr(settings, 'PINECONE_ENVIRONMENT', 'us-east-1')
PINECONE_NAMESPACE = getattr(settings, 'PINECONE_NAMESPACE', '')  # Default namespace

# Embedding dimension for all-MiniLM-L6-v2
EMBEDDING_DIMENSION = 384

# Rate limiting and retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 1.0  # seconds
BATCH_SIZE = 100
BATCH_DELAY = 0.5  # seconds between batches

# History settings
MAX_HISTORY_MESSAGES = 100


# ============================================================================
# KEYWORD EXTRACTION (TF-IDF BASED - NO MODEL DOWNLOADS)
# ============================================================================

class TFIDFKeywordExtractor:
    """
    Fast keyword extraction using TF-IDF
    No model downloads required, purely statistical approach
    """
    
    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            max_features=50,
            ngram_range=(1, 2),
            stop_words='english',
            lowercase=True,
            max_df=0.85,
            min_df=1
        )
    
    def extract_keywords(self, text: str, top_n: int = 10) -> List[str]:
        """
        Extract top keywords from text using TF-IDF
        
        Args:
            text: Input text
            top_n: Number of keywords to extract
        
        Returns:
            List of keyword strings
        """
        if not text or len(text.strip()) < 10:
            return []
        
        try:
            # TF-IDF needs a corpus, so we split text into sentences
            sentences = [s.strip() for s in text.split('.') if len(s.strip()) > 10]
            
            if len(sentences) < 2:
                # If very short, just split into words
                words = text.lower().split()
                # Filter out common words manually
                common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for'}
                keywords = [w for w in words if w not in common_words and len(w) > 3]
                return keywords[:top_n]
            
            # Fit and transform
            tfidf_matrix = self.vectorizer.fit_transform(sentences)
            
            # Get feature names (words/phrases)
            feature_names = self.vectorizer.get_feature_names_out()
            
            # Calculate average TF-IDF scores across all sentences
            avg_scores = np.asarray(tfidf_matrix.mean(axis=0)).ravel()
            
            # Get top N indices
            top_indices = avg_scores.argsort()[-top_n:][::-1]
            
            # Return top keywords
            keywords = [feature_names[i] for i in top_indices if avg_scores[i] > 0]
            
            return keywords
        
        except Exception as e:
            logger.warning(f"TF-IDF keyword extraction failed: {e}")
            # Fallback: simple word frequency
            words = text.lower().split()
            word_freq = {}
            for word in words:
                if len(word) > 3:
                    word_freq[word] = word_freq.get(word, 0) + 1
            
            sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
            return [word for word, _ in sorted_words[:top_n]]


# ============================================================================
# MAIN RETRIEVAL SYSTEM
# ============================================================================

class AdRetrievalSystem:
    """
    Production-ready ad retrieval system with:
    - Pinecone for vector storage (with metadata)
    - HuggingFace API for embeddings
    - TF-IDF for keyword extraction
    - No local file dependencies
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        logger.info("Initializing Ad Retrieval System (Production Version)...")
        
        # Validate API keys
        if not HUGGINGFACE_API_KEY:
            raise ValueError("HUGGINGFACE_API_KEY is not configured")
        if not PINECONE_API_KEY:
            raise ValueError("PINECONE_API_KEY is not configured")
        
        # Initialize HuggingFace Inference API embeddings
        self.embeddings = HuggingFaceEndpointEmbeddings(
            model=EMBEDDING_MODEL,
            huggingfacehub_api_token=HUGGINGFACE_API_KEY,
            task="feature-extraction",
        )
        
        # Initialize TF-IDF keyword extractor (no downloads!)
        self.keyword_extractor = TFIDFKeywordExtractor()
        
        # Initialize Pinecone
        self.pc = Pinecone(api_key=PINECONE_API_KEY)
        self.index_name = PINECONE_INDEX_NAME
        self.namespace = PINECONE_NAMESPACE
        
        # Initialize index handle (native Pinecone client only)
        self.index = None
        
        # Load or create index
        self._load_or_create_vectorstore()
        
        self._initialized = True
        logger.info("Ad Retrieval System initialized successfully")
    
    # ========================================================================
    # CORE RETRIEVAL WITH QUERY PRIORITIZATION
    # ========================================================================
    
    def retrieve_ads(
        self, 
        user_query: str,
        user_preferences: List[str],
        chat_history: List[str],
        opt_out: bool = False,
        limit: int = 3
    ) -> List[int]:
        """
        Two-Step Hybrid Retrieval with Query Prioritization
        
        Step 1: Main Search (70%) - Focused on current query
        Step 2: Broad Search (30%) - Context from history + preferences
        
        Args:
            user_query: Current user message (PRIORITIZED)
            user_preferences: User's interest categories
            chat_history: Previous chat messages
            opt_out: Whether user opted out
            limit: Number of ads to return
        
        Returns:
            List of ad IDs ranked by relevance (query-first)
        """
        # Handle opt-out
        if opt_out:
            return []
        
        # Check if index has ads
        if not self._has_ads():
            logger.warning("No ads in vectorstore")
            return []
        
        try:
            # ===== STEP 1: MAIN SEARCH - Query Focused (70% of results) =====
            main_candidates = self._main_search_query_focused(
                user_query=user_query,
                k=limit * 4  # Get more candidates for better diversity
            )
            
            # ===== STEP 2: BROAD SEARCH - Context Aware (30% of results) =====
            broad_candidates = self._broad_search_context_aware(
                user_query=user_query,
                chat_history=chat_history,
                user_preferences=user_preferences,
                k=limit * 2
            )
            
            # ===== STEP 3: MERGE & DEDUPLICATE =====
            merged_candidates = self._merge_results(
                main_results=main_candidates,
                broad_results=broad_candidates,
                main_weight=0.7,
                limit=limit * 2
            )
            
            # ===== STEP 4: EXTRACT AD IDs =====
            ad_ids = self._extract_ad_ids(merged_candidates[:limit])
            
            logger.info(
                f"Retrieved {len(ad_ids)} ads (Query-prioritized) for: {user_query[:50]}..."
            )
            return ad_ids
        
        except Exception as e:
            logger.error(f"Retrieval failed: {e}", exc_info=True)
            return []
    
    def _main_search_query_focused(self, user_query: str, k: int) -> List[AdDocument]:
        """
        Main Search: Heavily weighted toward current query
        Uses query repetition to boost importance
        """
        # Repeat query 3x to boost its importance in embedding
        main_query = " ".join([user_query] * 3)
        
        logger.debug(f"Main search query: {user_query[:100]}... [3x repetition]")
        
        return self._vector_search(main_query, k)
    
    def _broad_search_context_aware(
        self, 
        user_query: str,
        chat_history: List[str],
        user_preferences: List[str],
        k: int
    ) -> List[AdDocument]:
        """
        Broad Search: Includes history + preferences (secondary importance)
        """
        search_parts = [user_query]  # Query appears once
        
        # Add history keywords
        if chat_history:
            history_keywords = self._extract_keywords_from_history(chat_history)
            if history_keywords:
                search_parts.append("Context: " + " ".join(history_keywords[:90]))
        
        # Add user preferences
        if user_preferences:
            search_parts.append("Interests: " + " ".join(user_preferences[:]))
        
        broad_query = " | ".join(search_parts)
        
        logger.debug(f"Broad search query: {broad_query[:100]}...")
        
        return self._vector_search(broad_query, k)
    
    def _merge_results(
        self,
        main_results: List[AdDocument],
        broad_results: List[AdDocument],
        main_weight: float = 0.7,
        limit: int = 10
    ) -> List[AdDocument]:
        """
        Merge results with priority to main search
        """
        main_count = int(limit * main_weight)
        
        seen_ad_ids: Set[int] = set()
        merged = []
        
        # Add main results first (70%)
        for doc in main_results:
            ad_id = self._get_ad_id_from_doc(doc)
            if ad_id and ad_id not in seen_ad_ids:
                merged.append(doc)
                seen_ad_ids.add(ad_id)
                if len(merged) >= main_count:
                    break
        
        # Add broad results (30%)
        for doc in broad_results:
            ad_id = self._get_ad_id_from_doc(doc)
            if ad_id and ad_id not in seen_ad_ids:
                merged.append(doc)
                seen_ad_ids.add(ad_id)
                if len(merged) >= limit:
                    break
        
        logger.info(f"Merged {len(merged)} unique ads (70/30 split)")
        
        return merged
    
    # ========================================================================
    # KEYWORD EXTRACTION (TF-IDF BASED)
    # ========================================================================
    
    def _extract_keywords_from_history(
        self, 
        chat_history: List[str],
        top_n: int = 10
    ) -> List[str]:
        """Extract keywords from chat history using TF-IDF"""
        if not chat_history:
            return []
        
        # Use last N messages
        recent_history = chat_history[-MAX_HISTORY_MESSAGES:]
        combined_text = " ".join(recent_history)
        
        # Skip if too short
        if len(combined_text.split()) < 10:
            return []
        
        return self.keyword_extractor.extract_keywords(combined_text, top_n)
    
    # ========================================================================
    # VECTOR SEARCH (NATIVE PINECONE)
    # ========================================================================
    
    def _vector_search(self, query: str, k: int) -> List[AdDocument]:
        """
        Embed the query, then search Pinecone natively.
        
        Returns:
            List of AdDocument objects with metadata
        """
        try:
            # Embed the query text using HuggingFace
            query_vector = self.embeddings.embed_query(query)
            
            # Build kwargs; only include namespace if non-empty
            query_kwargs = dict(
                vector=query_vector,
                top_k=k,
                include_metadata=True,
            )
            if self.namespace:
                query_kwargs["namespace"] = self.namespace
            
            # Query Pinecone directly
            results = self.index.query(**query_kwargs)
            
            # Convert matches → AdDocument list
            documents: List[AdDocument] = []
            for match in results.get("matches", []):
                metadata = match.get("metadata", {})
                documents.append(AdDocument(
                    page_content=metadata.get("text", ""),
                    metadata=metadata,
                ))
            
            return documents
        
        except Exception as e:
            logger.error(f"Vector search failed: {e}", exc_info=True)
            return []
    
    # ========================================================================
    # METADATA HELPERS (PINECONE-NATIVE)
    # ========================================================================
    
    def _get_ad_id_from_doc(self, doc: AdDocument) -> Optional[int]:
        """
        Extract ad_id from document metadata
        
        Pinecone metadata structure:
        {
            'ad_id': 123,
            'category': 'Sports',
            'title': 'Ad Title'
        }
        """
        try:
            return int(doc.metadata.get('ad_id'))
        except (ValueError, TypeError):
            logger.warning(f"Invalid ad_id in document metadata: {doc.metadata}")
            return None
    
    def _extract_ad_ids(self, documents: List[AdDocument]) -> List[int]:
        """Extract ad IDs from documents"""
        ad_ids = []
        for doc in documents:
            ad_id = self._get_ad_id_from_doc(doc)
            if ad_id:
                ad_ids.append(ad_id)
        return ad_ids
    
    def _has_ads(self) -> bool:
        """Check if index has any ads"""
        try:
            stats = self.index.describe_index_stats()
            total_vectors = stats.get('total_vector_count', 0)
            
            # Check specific namespace if used
            if self.namespace:
                namespace_stats = stats.get('namespaces', {}).get(self.namespace, {})
                total_vectors = namespace_stats.get('vector_count', 0)
            
            return total_vectors > 0
        except Exception as e:
            logger.error(f"Failed to check index stats: {e}")
            return False
    
    # ========================================================================
    # PINECONE INDEX MANAGEMENT (NATIVE CLIENT)
    # ========================================================================
    
    def _load_or_create_vectorstore(self):
        """Load existing Pinecone index or create new one"""
        try:
            existing_indexes = self.pc.list_indexes().names()
            
            if self.index_name not in existing_indexes:
                self._create_pinecone_index()
                # Wait for index to be ready
                self._wait_for_index_ready()
            
            # Connect to index (native Pinecone client)
            self.index = self.pc.Index(self.index_name)
            
            logger.info(f"Connected to Pinecone index: {self.index_name}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Pinecone: {e}", exc_info=True)
            raise
    
    def _create_pinecone_index(self):
        """Create new Pinecone index"""
        try:
            logger.info(f"Creating new Pinecone index: {self.index_name}")
            
            self.pc.create_index(
                name=self.index_name,
                dimension=EMBEDDING_DIMENSION,
                metric='cosine',
                spec=ServerlessSpec(
                    cloud='aws',
                    region=PINECONE_ENVIRONMENT
                )
            )
            
            logger.info(f"Pinecone index created: {self.index_name}")
            
        except Exception as e:
            logger.error(f"Failed to create Pinecone index: {e}", exc_info=True)
            raise
    
    def _wait_for_index_ready(self, timeout: int = 60):
        """Wait for index to be ready after creation"""
        logger.info("Waiting for index to be ready...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                desc = self.pc.describe_index(self.index_name)
                if desc.status.get('ready'):
                    logger.info("Index is ready")
                    return
            except Exception as e:
                logger.debug(f"Index not ready yet: {e}")
            
            time.sleep(2)
        
        raise TimeoutError(f"Index {self.index_name} not ready after {timeout}s")
    
    # ========================================================================
    # AD SYNC (NATIVE PINECONE UPSERT)
    # ========================================================================
    
    def add_or_update_ad(self, ad_id: int, ad_data: Dict):
        """
        Add new ad or update existing one
        
        Args:
            ad_id: Ad primary key (used directly as Pinecone ID)
            ad_data: Dict with 'title', 'description', 'category', 'target_keywords'
        """
        try:
            # Build document content
            content = self._build_ad_content(ad_data)
            
            # Embed the content
            vector = self.embeddings.embed_documents([content])[0]
            
            # Use ad_id directly for Pinecone vector ID
            pinecone_id = f"ad_{ad_id}"
            
            # Build metadata (stored alongside the vector in Pinecone)
            metadata = {
                'ad_id': ad_id,
                'category': ad_data.get('category', ''),
                'title': ad_data.get('title', ''),
                'description': ad_data.get('description', '')[:500],  # Truncate if too long
                'text': content,  # Store raw text so we can reconstruct AdDocument on retrieval
            }
            
            # Upsert with retry logic (upsert handles insert OR update)
            self._upsert_with_retry(
                vectors=[(pinecone_id, vector, metadata)]
            )
            
            logger.info(f"Added/updated ad {ad_id}")
        
        except Exception as e:
            logger.error(f"Failed to add ad {ad_id}: {e}", exc_info=True)
            raise
    
    def delete_ad(self, ad_id: int):
        """Delete ad from Pinecone"""
        try:
            pinecone_id = f"ad_{ad_id}"
            
            # Delete kwargs
            delete_kwargs = dict(ids=[pinecone_id])
            if self.namespace:
                delete_kwargs["namespace"] = self.namespace
            
            # Delete from Pinecone
            self.index.delete(**delete_kwargs)
            
            logger.info(f"Deleted ad {ad_id}")
        
        except Exception as e:
            logger.error(f"Failed to delete ad {ad_id}: {e}", exc_info=True)
            # Don't raise - deletion of non-existent ad is okay
    
    def bulk_index_all_ads(self) -> int:
        """
        Index all active ads from database
        """
        try:
            from advertisers.models import AdvertiserAd
            
            ads = AdvertiserAd.objects.filter(is_active=True)
            return self._bulk_index_ads(ads)
        
        except Exception as e:
            logger.error(f"Bulk indexing failed: {e}", exc_info=True)
            return 0
    
    def _bulk_index_ads(self, ads_queryset) -> int:
        """
        Internal method to bulk index ads with batch processing
        """
        if not ads_queryset.exists():
            logger.warning("No ads to index")
            return 0
        
        # Clear existing index
        try:
            logger.info("Clearing existing index...")
            delete_kwargs = dict(delete_all=True)
            if self.namespace:
                delete_kwargs["namespace"] = self.namespace
            self.index.delete(**delete_kwargs)
            time.sleep(2)  # Wait for deletion to complete
        except Exception as e:
            logger.warning(f"Could not clear index: {e}")
        
        # Prepare all (id, content) pairs — embed in batches below
        pending: List[tuple] = []  # (pinecone_id, content_str, metadata_dict)
        
        for ad in ads_queryset:
            ad_data = {
                'title': ad.title,
                'description': ad.description,
                'category': ad.category,
                'target_keywords': ad.target_keywords
            }
            
            content = self._build_ad_content(ad_data)
            pinecone_id = f"ad_{ad.id}"
            
            metadata = {
                'ad_id': ad.id,
                'category': ad.category,
                'title': ad.title,
                'description': ad.description[:500],
                'text': content,
            }
            
            pending.append((pinecone_id, content, metadata))
        
        # Batch: embed + upsert
        total_uploaded = 0
        
        for i in range(0, len(pending), BATCH_SIZE):
            batch = pending[i:i + BATCH_SIZE]
            
            # --- embed the batch of content strings at once ---
            contents = [item[1] for item in batch]
            
            for attempt in range(MAX_RETRIES):
                try:
                    vectors_list = self.embeddings.embed_documents(contents)
                    break  # success
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        logger.warning(f"Embedding batch failed (attempt {attempt + 1}), retrying: {e}")
                        time.sleep(RETRY_DELAY * (attempt + 1))
                    else:
                        logger.error(f"Embedding batch failed after {MAX_RETRIES} attempts: {e}")
                        vectors_list = None
            
            if vectors_list is None:
                continue  # skip this batch on total failure
            
            # --- build upsert payload: list of (id, vector, metadata) ---
            upsert_vectors = [
                (batch[j][0], vectors_list[j], batch[j][2])
                for j in range(len(batch))
            ]
            
            # --- upsert with retry ---
            for attempt in range(MAX_RETRIES):
                try:
                    self._upsert_with_retry(vectors=upsert_vectors)
                    total_uploaded += len(batch)
                    logger.info(f"Uploaded batch {i // BATCH_SIZE + 1}: {len(batch)} ads")
                    break
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        logger.warning(f"Upsert batch failed (attempt {attempt + 1}), retrying: {e}")
                        time.sleep(RETRY_DELAY * (attempt + 1))
                    else:
                        logger.error(f"Upsert batch failed after {MAX_RETRIES} attempts: {e}")
            
            # Delay between batches to respect rate limits
            if i + BATCH_SIZE < len(pending):
                time.sleep(BATCH_DELAY)
        
        logger.info(f"Bulk indexed {total_uploaded}/{len(pending)} ads")
        return total_uploaded
    
    def _upsert_with_retry(self, vectors: List[tuple]):
        """
        Upsert vectors into Pinecone with retry logic.
        
        Args:
            vectors: List of (id, vector, metadata) tuples
        """
        upsert_kwargs = dict(vectors=vectors)
        if self.namespace:
            upsert_kwargs["namespace"] = self.namespace
        
        for attempt in range(MAX_RETRIES):
            try:
                self.index.upsert(**upsert_kwargs)
                return  # success
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"Upsert failed (attempt {attempt + 1}), retrying: {e}")
                    time.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"Upsert failed after {MAX_RETRIES} attempts: {e}")
                    raise
    
    def _build_ad_content(self, ad_data: Dict) -> str:
        """Build rich text content for ad embedding"""
        parts = []
        
        if ad_data.get('title'):
            parts.append(ad_data['title'])
        
        if ad_data.get('description'):
            parts.append(ad_data['description'])
        
        if ad_data.get('category'):
            parts.append(f"Category: {ad_data['category']}")
        
        if ad_data.get('target_keywords'):
            keywords = ad_data['target_keywords']
            if isinstance(keywords, list):
                parts.append(" ".join(keywords))
            elif isinstance(keywords, str):
                parts.append(keywords)
        
        return " | ".join(parts)
    
    # ========================================================================
    # UTILITY METHODS
    # ========================================================================
    
    def get_index_stats(self) -> Dict:
        """Get statistics about the index"""
        try:
            stats = self.index.describe_index_stats()
            return {
                'total_vectors': stats.get('total_vector_count', 0),
                'dimension': stats.get('dimension', 0),
                'namespaces': stats.get('namespaces', {})
            }
        except Exception as e:
            logger.error(f"Failed to get index stats: {e}")
            return {}
    
    def list_all_ad_ids(self) -> List[int]:
        """
        List all ad IDs in the index
        Note: This uses Pinecone's query API (limited to 10k results)
        """
        try:
            # Query with a dummy vector to get all results
            query_kwargs = dict(
                vector=[0.0] * EMBEDDING_DIMENSION,
                top_k=10000,
                include_metadata=True,
            )
            if self.namespace:
                query_kwargs["namespace"] = self.namespace
            
            results = self.index.query(**query_kwargs)
            
            ad_ids = []
            for match in results.get('matches', []):
                ad_id = match.get('metadata', {}).get('ad_id')
                if ad_id:
                    ad_ids.append(int(ad_id))
            
            return ad_ids
        
        except Exception as e:
            logger.error(f"Failed to list ad IDs: {e}")
            return []


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

# Global instance
_retrieval_system = None
_init_lock = threading.Lock()
def get_retrieval_system() -> AdRetrievalSystem:
    """Get singleton instance"""
    global _retrieval_system
    if _retrieval_system is None:
     with _init_lock:
      if _retrieval_system is None:
        _retrieval_system = AdRetrievalSystem()
    return _retrieval_system


def retrieve_ads_for_user(
    user, 
    query: str, 
    chat_history: List[str] = None, 
    limit: int = 3
) -> List[int]:
    """
    Convenience function to retrieve ads for a user
    
    Args:
        user: Django User object
        query: Current user message (PRIORITIZED)
        chat_history: List of previous messages
        limit: Number of ads to return
    
    Returns:
        List of ad IDs
    """
    from user.models import UserPreference
    
    # Get user preferences
    try:
        prefs = UserPreference.objects.get(user=user)
        opt_out = prefs.complete_opt_out
        categories = prefs.interest_categories or []
    except UserPreference.DoesNotExist:
        opt_out = False
        categories = []
    
    # Retrieve ads
    system = get_retrieval_system()
    return system.retrieve_ads(
        user_query=query,
        user_preferences=categories,
        chat_history=chat_history or [],
        opt_out=opt_out,
        limit=limit
    )