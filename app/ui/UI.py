import gradio as gr
import random

def random_response(message, history):
    return random.choice(["Nice to meet you", "How can i help you", "hi there how's going!"])


# Execute chat bot Interface #
gr.ChatInterface(
    fn=random_response, 
).launch()