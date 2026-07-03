from llm import llm

question = "how many number of employees within this employee table?"
response = llm.invoke(question)
print(response.content)