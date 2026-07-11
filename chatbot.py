import anthropic

client = anthropic.Anthropic()
MODEL_NAME = "claude-sonnet-5"


def add_user_message(messages, text):
    messages.append({"role": "user", "content": text})


def add_assistant_message(messages, text):
    messages.append({"role": "assistant", "content": text})


def chat(messages):
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=1000,
        messages=messages,
    )
    return response.content[0].text


def main():
    # Initial list of messages
    messages = []

    # Run the chatbot forever
    while True:
        user_input = input("> ")

        # Add user input to the list of messages
        add_user_message(messages, user_input)
        # Call Claude with the chat function
        answer = chat(messages)
        # Add generated text to the list of messages
        add_assistant_message(messages, answer)

        # Print the generated text
        print("---")
        print(answer)
        print("---")


if __name__ == "__main__":
    main()
