import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


llm = ChatOpenAI(
    model="google/gemini-2.5-flash",
    base_url=os.environ["LITELLM_URL"],
    api_key=os.environ["API_KEY"],
    temperature=0.3
)

# test standalone function #
if __name__ == "__main__":
    question = input("Enter your question: ")
    response = llm.invoke(question)
    print(response.content)
