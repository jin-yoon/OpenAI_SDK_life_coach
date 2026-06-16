from openai.types.responses.web_search_tool import UserLocation
import streamlit as st
import dotenv
import asyncio
from agents import (
    Agent,
    Runner,
    SQLiteSession,
    WebSearchTool,
)

dotenv.load_dotenv()

st.header("👩🏻‍🏫 Life Coach Agent")

if "agent" not in st.session_state:
    st.session_state["agent"] = Agent(
        name="Life Coach Agent",
        # instructions="""
        # 너는 life coach로, user의 삶이 더 나아질 수 있도록 동기부여하는 역할이야.
        # You have access to the following tools :
        #     - Web Search Tool : 사용자의 질문의 point를 파악하고, 이에 대한 해결방안을 검색하는 도구(ex. "잠이 안오는데, 어떻게 해야 잘 수 있을까?" -> "잠 잘자는 법" 검색)
        #                         동기부여, 자기 개발 팁, 습관 형성 조언 등에 대한 답변을 할 때, 우선적으로 web에 검색해서 제공해주고, url은 노출하지 마.
        # """,
        instructions="""
        You are a web-based helpful&friendly life coach. 
        You have access to the following tools:
            - Web Search Tool : 
                            - Always use this tool for questions related to self-improvement, habit formation, and motivational content. 
                              (Example: "How can I wake up early in the morning?" → use web search with the query "how to wake up early.")
                            - 답변할 때 출처/인용 표시를 하지 말고, 웹을 사용하더라도 자연스럽게 요약만 해줘(웹 검색이 필요하더라도 본문에 citation, 출처 표기, 링크를 넣지 말고, 결과만 간단히 정리해줘.)
                    """,
        tools=[
            WebSearchTool(),
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
                    st.write(f"✅ <{query}> 검색완료")


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
    "당신의 <인생코치>와 상담하세요!",
)

if prompt:
    with st.chat_message("human"):
        st.write(prompt)
    asyncio.run(run_agent(prompt))

reset = st.button("Reset Memory")
if reset:
    asyncio.run(session.clear_session())
