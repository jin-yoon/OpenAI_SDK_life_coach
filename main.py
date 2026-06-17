from pydoc import cli
from openai.types.responses.web_search_tool import UserLocation
import streamlit as st
import dotenv
import asyncio
from openai import OpenAI
from pydantic import BaseModel, Field
from agents import (
    Agent,
    Runner,
    SQLiteSession,
    WebSearchTool,
    FileSearchTool,
)

dotenv.load_dotenv()
client = OpenAI()


# class Answer(BaseModel):
#     user_situation: str = Field(
#         description="User's past records, uploaded files, goals, plans, and previous progress to understand their situation."
#     )
#     improvement_point: str = Field(
#         description="Identify improvement areas based on their history(user_situation)"
#     )
#     advice: str = Field(
#         description="Provide personalized recommendations with Web Search Tool."
#     )


VECTOR_STORE_ID = "vs_6a3234fd3fb881918bb0e451d28d9c5c"

st.title("LIFE COACH AGENT")
st.caption("     Feel free to ask me anything! - No scams, no tricks😉")

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
            Search the web for relevant strategies, scientific evidence, expert recommendations, or practical methods related to the identified improvement areas.

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
        ],
    )
agent = st.session_state["agent"]

# initialize session - 최초 1회만 실행
if "session" not in st.session_state:
    st.session_state["session"] = SQLiteSession(
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
                    st.write(content)
                else:
                    if message["type"] == "message":
                        st.write(message["content"][0]["text"])
        if "type" in message:
            if message["type"] == "web_search_call":
                query = message["action"]["queries"][-1]
                with st.chat_message("ai"):
                    st.write(f'✅ 검색완료 : "{query}"')


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
        response = ""

        stream = Runner.run_streamed(agent, message, session=session)
        async for event in stream.stream_events():
            if event.type == "raw_response_event":
                update_status(status_container, event.data.type)
                if event.data.type == "response.output_text.delta":
                    response += event.data.delta
                    text_placeholder.write(response)


prompt = st.chat_input(
    "Consulting with your life coach!", accept_file=True, file_type=["txt", "pdf"]
)
if prompt:
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
