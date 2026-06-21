import streamlit as st
import dotenv
import asyncio
from openai import OpenAI
import copy
import base64
from agents import (
    Agent,
    Runner,
    SQLiteSession,
    WebSearchTool,
    FileSearchTool,
    ImageGenerationTool,
)

dotenv.load_dotenv()
client = OpenAI()

VECTOR_STORE_ID = "vs_6a3234fd3fb881918bb0e451d28d9c5c"

# class FilteredSQLiteSession(SQLiteSession):

#     def __init__(self, session_id: str, database: str):
#         super().__init__(session_id, database)

#     # 모든 dict/list 내부를 재귀적으로 탐색하면서 제거
#     def _clean_recursive(self, obj):

#         if isinstance(obj, dict):

#             cleaned = {}

#             for k, v in obj.items():

#                 # 제거할 필드
#                 if k in ["action", "annotations"]:
#                     continue

#                 cleaned[k] = self._clean_recursive(v)

#             return cleaned

#         elif isinstance(obj, list):

#             return [self._clean_recursive(item) for item in obj]

#         else:
#             return obj

#     # 저장 전에 필터링
#     async def add_items(self, items):

#         cleaned_items = [self._clean_recursive(copy.deepcopy(item)) for item in items]

#         await super().add_items(cleaned_items)

#     # 읽을 때도 한번 더 필터링
#     async def get_items(self):

#         items = await super().get_items()

#         cleaned_items = [self._clean_recursive(copy.deepcopy(item)) for item in items]

#         return cleaned_items


class FilteredSQLiteSession(SQLiteSession):

    def __init__(self, session_id: str, database: str):
        super().__init__(session_id, database)

    def _remove_action_recursive(self, obj):

        if isinstance(obj, dict):

            cleaned = {
                k: v for k, v in obj.items() if k not in ["action", "annotations"]
            }

            return {k: self._remove_action_recursive(v) for k, v in cleaned.items()}

        elif isinstance(obj, list):

            return [self._remove_action_recursive(item) for item in obj]

        else:
            return obj

    async def get_items(self):

        items = await super().get_items()

        return [self._remove_action_recursive(copy.deepcopy(item)) for item in items]


st.title("🌟LIFE COACH AGENT")
st.caption(
    "     Feel free to ask me anything! - How to achieve your goal, Tips for self-development, motivation..."
)

if "agent" not in st.session_state:
    st.session_state["agent"] = Agent(
        name="Life Coach Agent",
        instructions="""
        You are a friendly personal life coach.
        Your job is to analyze the user's past behavior and provide actionable improvement advice.

        You have access to:
        1. File Search Tool:
            - Use this to retrieve the user's personal records, goals, habits, journals, and previous conversations.
            - Always use this first when the question is related to the user's personal progress.

        2. Web Search Tool:
            - Use this to find external, up-to-date, evidence-based advice, methods, routines, or strategies.
            - When you identify an improvement point from user data, you MUST use Web Search to find relevant recommendations.

        Follow this workflow for personal improvement questions:

            Step 1.
            Analyze the user's personal data using File Search.

            Step 2.
            Identify:
            - current status
            - progress toward goals
            - problems or patterns
            - areas for improvement

            Step 3.
            USE WebSearchTool for relevant strategies, scientific evidence, expert recommendations, or practical methods related to the identified improvement areas.

            Step 4.
            Combine both sources:
            - First explain the user's current situation based on File Search.
            - Then provide improvement suggestions supported by Web Search results.

            Example:

            User:
            "How is my exercise goal going?"

            Correct behavior:

            File Search:
            "Based on your records, you planned to run 3 times per week. Recently you completed 2 sessions per week..."

            Then Web Search:
            "Research effective methods to maintain running habits..."

            Final answer:
            "Your current progress is... 
            To improve consistency, here are strategies based on recent research..."

            Never provide only File Search results when the user asks for advice, improvement, habits, goals, routines, or self-development.
  
                    """,
        tools=[
            WebSearchTool(),
            FileSearchTool(
                vector_store_ids=[VECTOR_STORE_ID],
                max_num_results=3,
            ),
            ImageGenerationTool(
                tool_config={
                    "type": "image_generation",
                    "quality": "low",
                    "output_format": "jpeg",
                    "moderation": "low",
                    "partial_images": 1,
                    "size": "1024x1024",
                }
            ),
        ],
    )

agent = st.session_state["agent"]

# initialize session - 최초 1회만 실행
if "session" not in st.session_state:
    st.session_state["session"] = FilteredSQLiteSession(
        "chat-history",
        "life-coach-memory.db",
    )

session = st.session_state["session"]


# -------- 함수 생성 ----------
async def paint_history():
    messages = await session.get_items()
    for message in messages:
        if "role" in message:
            with st.chat_message(message["role"]):
                if message["role"] == "user":
                    content = message["content"]
                    if isinstance(content, str):
                        st.write(content)
                    elif isinstance(content, list):
                        for part in content:
                            if "image_url" in part and part["type"] == "input_image":
                                st.image(part["image_url"])
                else:
                    if message["type"] == "message":
                        st.write(message["content"][0]["text"])
        if "type" in message:
            message_type = message["type"]
            if message_type == "web_search_call":
                with st.chat_message("ai"):
                    st.write(f"✅ Web search completed!")
            elif message_type == "file_search_call":
                with st.chat_message("ai"):
                    st.write("🗂️Searched your files....")
            elif message_type == "image_generation_call":
                image = base64.b64decode(message["result"])
                with st.chat_message("ai"):
                    st.image(image)


def update_status(status_container, event):
    status_messages = {
        "response.web_search_call.completed": ("👍 Web Search 완료!", "complete"),
        "response.web_search_call.in_progress": (
            "👩‍💻 Web Search 시작!",
            "running",
        ),
        "response.web_search_call.searching": (
            "👀 검색 중...",
            "running",
        ),
        "response.file_search_call.completed": ("👍 File Search 완료!", "complete"),
        "response.file_search_call.in_progress": (
            "👩‍💻 File Search 시작!",
            "running",
        ),
        "response.file_search_call.searching": (
            "👀 파악 중...",
            "running",
        ),
        "response.image_generation_call.generating": (
            "✍️ Drawing image...",
            "running",
        ),
        "response.image_generation_call.in_progress": (
            "🎨 Drawing image...",
            "running",
        ),
        "response.completed": (f"✅ 완료", "complete"),
    }

    if event in status_messages:
        label, state = status_messages[event]
        status_container.update(label=label, state=state)


asyncio.run(paint_history())


async def run_agent(message):
    with st.chat_message("ai"):
        status_container = st.status("⏳..", expanded=False)
        text_placeholder = st.empty()
        image_placeholder = st.empty()
        response = ""

        st.session_state["image_placeholder"] = image_placeholder
        st.session_state["text_placeholder"] = text_placeholder

        stream = Runner.run_streamed(agent, message, session=session)
        async for event in stream.stream_events():
            if event.type == "raw_response_event":
                update_status(status_container, event.data.type)
                if event.data.type == "response.output_text.delta":
                    response += event.data.delta
                    text_placeholder.write(response)
                elif event.data.type == "response.image_generation_call.partial_image":
                    image = base64.b64decode(event.data.partial_image_b64)
                    image_placeholder.image(image)


prompt = st.chat_input(
    "Consulting with your life coach!", accept_file=True, file_type=["txt", "pdf"]
)
if prompt:
    if "image_placeholder" in st.session_state:
        st.session_state["image_placeholder"].empty()
    if "text_placeholder" in st.session_state:
        st.session_state["text_placeholder"].empty()

    for file in prompt.files:
        if file.type.startswith("text/") or file.type.startswith("pdf/"):
            with st.chat_message("ai"):
                with st.status("⏳ Uploading file....") as status:
                    uploaded_file = client.files.create(
                        file=(
                            file.name,
                            file.getvalue(),
                        ),
                        purpose="user_data",
                    )
                    status.update(label="⌛️ Attaching file...")
                    client.vector_stores.files.create(
                        vector_store_id=VECTOR_STORE_ID,
                        file_id=uploaded_file.id,
                    )

                    vector_file = client.vector_stores.files.retrieve(
                        vector_store_id=VECTOR_STORE_ID,
                        file_id=uploaded_file.id,
                    )
                    while vector_file.status != "completed":
                        vector_file = client.vector_stores.files.retrieve(
                            vector_store_id=VECTOR_STORE_ID,
                            file_id=uploaded_file.id,
                        )
                    status.update(label="👍 Uploaded successfully!", state="complete")

    if prompt.text:
        with st.chat_message("human"):
            st.write(prompt.text)
        asyncio.run(run_agent(prompt.text))

reset = st.button("Reset Memory")
if reset:
    asyncio.run(session.clear_session())


# 챗봇의 메모리를 볼 수 있는 디버깅 사이드바 만들기
with st.sidebar:

    st.write(
        asyncio.run(session.get_items())
    )  # asyncio.run() : event loop를 실행시켜주는 역할
