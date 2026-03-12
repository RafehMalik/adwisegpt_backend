"""
LLM Service for AdWiseGPT
Pure conversational AI — no ad blending, no ad scoring.
Ads are handled entirely by the separate /chat/ads/ endpoint.
"""

from typing import List, Dict
from pydantic import BaseModel, Field
import logging
import re
from django.conf import settings

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)


# ============================================================================
# GEMINI PROVIDER
# ============================================================================

class GoogleGeminiProvider:
    """Google Gemini 2.5 Flash"""

    def __init__(self):
        self.api_key = getattr(settings, 'GOOGLE_API_KEY', None)
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY not found in settings")
        self.llm = None

    def initialize(self):
        if self.llm:
            return self.llm

        self.llm = ChatGoogleGenerativeAI(
            model="models/gemini-2.5-flash",
            google_api_key=self.api_key,
            temperature=0.7,
            max_output_tokens=2048,
        )
        logger.info("Google Gemini 2.5 Flash initialized successfully")
        return self.llm

    def generate(self, messages: List) -> str:
        if not self.llm:
            self.initialize()
        response = self.llm.invoke(messages)
        return response.content
    


# ============================================================================
# MAIN LLM SERVICE
# ============================================================================

class LLMService:
    """
    Pure conversational LLM service.
    Receives a user message + chat history, returns a plain text response.
    No ad retrieval, no ad scoring, no ad blending.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return

        self.provider = GoogleGeminiProvider()
        self.provider.initialize()
        self._initialized = True
        logger.info("LLM Service initialized")

    def generate_response(
        self,
        user_message: str,
        session_id: str,
        chat_history: List[Dict] = None,
    ) -> str:
        """
        Generate a plain conversational AI response.

        Args:
            user_message:  Current user query.
            session_id:    Used for logging only.
            chat_history:  [{'role': 'user'|'assistant', 'content': '...'}, ...]

        Returns:
            str: AI response text.
        """
        try:
            messages = self._build_messages(
                user_message=user_message,
                chat_history=chat_history or [],
            )

            raw_response = self.provider.generate(messages)
            return self._clean_response(raw_response)

        except Exception as e:
            logger.error(f"LLM generation failed (session={session_id}): {e}", exc_info=True)
            return self._fallback_response(user_message)
    
   
    # -------------------------------------------------------------------------
    # MESSAGE BUILDER
    # -------------------------------------------------------------------------

    def _build_messages(self, user_message: str, chat_history: List[Dict]) -> List:
        messages = []

        # System prompt — conversational assistant, no ad instructions
        messages.append(SystemMessage(content=self._system_prompt()))

        # Chat history (last 10 turns)
        for msg in chat_history[:]:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            if role == 'user':
                messages.append(HumanMessage(content=content))
            elif role == 'assistant':
                messages.append(AIMessage(content=content))

        # Current user message
        messages.append(HumanMessage(content=user_message))
        return messages

    # -------------------------------------------------------------------------
    # SYSTEM PROMPT
    # -------------------------------------------------------------------------

#    @staticmethod
#     def _system_prompt() -> str:
#         return """You are AdWiseGPT, an expert AI assistant that provides accurate, helpful, and conversational responses.

# ## YOUR STYLE
# - **Conversational & Natural**: Respond like ChatGPT — friendly, clear, and helpful.
# - **Comprehensive but Concise**: Provide complete answers without unnecessary verbosity.
# - **Well-Structured**: Use markdown formatting (bold, bullets, headers) when it aids clarity.
# - **Accurate & Reliable**: Prioritize factual correctness above all.

# ## RESPONSE GUIDELINES
# 1. **Understand the question**: What is the user really asking?
# 2. **Provide value first**: Answer thoroughly and accurately.
# 3. **Professional tone**: Be helpful and friendly.

# ## FORMATTING
# - Use **bold** for emphasis.
# - Use bullet points for lists and numbered lists for steps.
# - Keep paragraphs 2–4 sentences long.

# Respond naturally and conversationally."""
    @staticmethod
    def _system_prompt() -> str:
     return """You are AdWiseGPT, a sharp and knowledgeable AI assistant. You give accurate, well-structured answers that feel like they came from a helpful expert — not a corporate chatbot.

## IDENTITY
- Name: AdWiseGPT
- Tone: confident, direct, friendly — like a knowledgeable colleague
- Expertise: technology, business, marketing, and general knowledge

---

## RESPONSE LENGTH
Match length to complexity:

| Question Type | Length | Example |
|---|---|---|
| Greetings / small talk | 1–2 sentences | "Hi, how are you?" |
| Simple factual | 2–4 sentences | "What is an API?" |
| Moderate explanation | Short sections with headers | "How does HTTPS work?" |
| Complex / multi-part | Full structured response | "Explain how to build a REST API" |

Never pad responses with filler. Stop when the answer is complete.

---

## FORMATTING

Use markdown in every response except greetings and very short answers.

**Headings:**
- `##` for main sections
- `###` for subsections
- Never use `#` (too large)

**Emphasis:**
- `**bold**` for key terms, important warnings, and critical steps
- `*italic*` for definitions or mild emphasis
- Never bold entire sentences

**Lists:**
- Use `-` for non-sequential items
- Use `1. 2. 3.` for steps, rankings, or ordered processes
- Keep list items parallel in structure

**Code:**
- Inline: backticks for `variable_names`, `functions()`, `commands`
- Block: triple backticks with language tag
```python
# Always include the language tag
def example():
    return "like this"
```

**Tables:** Use for comparisons, pros/cons, or structured data

**Blockquotes:** Use `>` for tips, warnings, or callouts
> **Note:** This is how you highlight important information.

**Dividers:** Use `---` to separate major sections in long responses

---

## NEVER DO
- Never start with "Great question!", "Certainly!", "Of course!", "Sure!" or similar filler
- Never repeat the user's question before answering
- Never add unnecessary disclaimers unless genuinely critical
- Never say "it depends" without immediately explaining what it depends on
- Never write walls of plain text — use structure for anything over 4 sentences

---

## EDGE CASES

**Greetings:** Respond warmly and briefly.
> User: "Hey!" → You: "Hey! What can I help you with today?"

**Unclear questions:** State your interpretation, then answer.
> "I'll take this as asking about X — here's the answer. If you meant something else, let me know."

**Unknown topics:** Be direct. Never hallucinate.
> "I don't have reliable information on that. Here's what I do know: ..."

**Opinion questions:** Give a reasoned take. No fence-sitting.

---

## EXAMPLE RESPONSE

**User:** How does JWT authentication work?

**You:**

JWT (JSON Web Token) is a compact, self-contained way to securely transmit information between a client and server.

## How It Works
1. **User logs in** — sends credentials to the server
2. **Server creates a JWT** — signs it with a secret key and returns it
3. **Client stores the token** — typically in memory or an httpOnly cookie
4. **Client sends token with every request** — in the `Authorization` header
5. **Server verifies the signature** — no database lookup needed

## JWT Structure
A JWT has three parts separated by dots: `header.payload.signature`
```json
{
  "user_id": 42,
  "email": "user@example.com",
  "exp": 1719000000
}
```

## When to Use JWT

| Use Case | Suitable? |
|---|---|
| Stateless APIs | ✅ Yes |
| Mobile apps | ✅ Yes |
| Sessions needing instant revocation | ❌ Prefer server sessions |

> **Security tip:** Never store JWTs in `localStorage` in high-security apps — use `httpOnly` cookies instead."""
    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------

    @staticmethod
    def _clean_response(response: str) -> str:
        response = response.replace("[INST]", "").replace("[/INST]", "")
        response = response.replace("<s>", "").replace("</s>", "")
        for phrase in ["As an AI assistant,", "As AdWiseGPT,", "I'm an AI", "I am an AI"]:
            response = response.replace(phrase, "")
        lines = [line.strip() for line in response.split('\n')]
        return '\n'.join(line for line in lines if line).strip()

    @staticmethod
    def _fallback_response(user_message: str) -> str:
        return (
            f"I understand you're asking about: '{user_message[:100]}'. "
            "I'm experiencing a temporary issue. Please try again in a moment."
        )


# ============================================================================
# SINGLETON & CONVENIENCE FUNCTION
# ============================================================================

_service_instance = None


def get_llm_service() -> LLMService:
    global _service_instance
    if _service_instance is None:
        _service_instance = LLMService()
    return _service_instance


def generate_chat_response(
    user_message: str,
    chat_history: List[Dict] = None,
    session_id: str = None,
    # sponsored_ads kept as an ignored kwarg so existing callers don't break
    sponsored_ads: List[Dict] = None,
) -> str:
    """
    Main entry point called from ChatView.

    Args:
        user_message:   User's current message.
        chat_history:   [{'role': 'user'|'assistant', 'content': '...'}, ...]
        session_id:     Session ID (logging only).
        sponsored_ads:  Accepted but ignored — ads are handled separately.

    Returns:
        str: Plain AI response text.
    """
    if not session_id:
        import uuid
        session_id = f"temp_{uuid.uuid4().hex[:8]}"

    service = get_llm_service()
    return service.generate_response(
        user_message=user_message,
        session_id=session_id,
        chat_history=chat_history,
    )
