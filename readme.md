# Generating Cypher Queries With ChatGPT

This code will show you how to implement a Cypher statement-generating model by providing only the graph schema information. We will evaluate the model’s Cypher construction capabilities on three graphs with different graph schemas. Currently, the only model I recommend to generate Cypher statements based on only the provided graph schema is GPT-4. Other models like GPT-3.5-turbo or text-davinci-003 aren’t that great, and I have yet to find an open-source LLM model that would be good at following instructions in the prompt and GPT-4.
Experiment Setup
I have implemented a Python class that connects to a Neo4j instance and fetches the schema information when initialized. The graph schema information can then be used as input to GPT-4 model.

```
class Neo4jGPTQuery:
    def __init__(self, url, user, password, openai_api_key):
        self.driver = GraphDatabase.driver(url, auth=(user, password))
        openai.api_key = openai_api_key
        # construct schema
        self.schema = self.generate_schema() 
```
The graph schema is stored in a string format with the following structure:
```
  f"This is the schema representation of the Neo4j database.
  Node properties are the following:
  {node_props}
  Relationship properties are the following:
  {rel_props}
  Relationship point from source to target nodes
  {rels}
  Make sure to respect relationship types and directions"
```
You can check the code if you are interested in the specific Cypher statements to retrieve schema information.

Next, we need to do a bit of prompt engineering and create a system prompt for the GPT-4 model that will be used to translate natural language into Cypher statements.
```
def get_system_message(self):
    return f"""
    Task: Generate Cypher queries to query a Neo4j graph database based on the provided schema definition.
    Instructions:
    Use only the provided relationship types and properties.
    Do not use any other relationship types or properties that are not provided.
    If you cannot generate a Cypher statement based on the provided schema, explain the reason to the user.
    Schema:
    {self.schema}

    Note: Do not include any explanations or apologies in your responses."""
```
It’s interesting how I ended with the final system message to get GPT-4 following my instructions. At first, I wrote my directions as plain text and added some constraints. However, the model wasn’t doing exactly what I wanted, so I opened ChatGPT in a web browser and asked GPT to rewrite my instructions in a manner that GPT-4 would understand. Finally, ChatGPT seems to understand what works best as GPT-4 prompts, as the model behaved much better with this new prompt structure.

Next, we need to define a function that will generate Cypher statements.
```
def construct_cypher(self, question, history=None):
    messages = [
        {"role": "system", "content": self.get_system_message()},
        {"role": "user", "content": question},
    ]
    # Used for Cypher healing flows
    if history:
        messages.extend(history)

    completions = openai.ChatCompletion.create(
        model="gpt-4",
        temperature=0.0,
        max_tokens=1000,
        messages=messages
    )
    return completions.choices[0].message.content
```
The GPT-4 model uses the ChatCompletion endpoint, which uses a combination of system, user, and optional assistant messages when we want to ask follow-up questions. So, we always start with only the system and user message. However, if the generated Cypher statement has any syntax error, the self-healing flow will be started, where we include the error in the follow-up question so that GPT-4 can fix the query. Therefore, we have included the optional history parameter for Cypher self-healing flow.

Don’t worry if the self-healing Cypher flow is a bit confusing. After, you will see the following run function, everything will make sense.
```
def run(self, question, history=None, retry=True):
    # Construct Cypher statement
    cypher = self.construct_cypher(question, history)
    print(cypher)
    try:
        return self.query_database(cypher)
    # If Cypher syntax error
    except CypherSyntaxError as e:
        # If out of retries
        if not retry:
          return "Invalid Cypher syntax"
        # Self-healing Cypher flow by
        # providing specific error to GPT-4
        print("Retrying")
        return self.run(
            question,
            [
                {"role": "assistant", "content": cypher},
                {
                    "role": "user",
                    "content": f"""This query returns an error: {str(e)} 
                    Give me a improved query that works without any explanations or apologies""",
                },
            ],
            retry=False
        )
```
The run function starts by generating a Cypher statement.
Then, the generated Cypher statement is used to query the Neo4j database.
If the Cypher syntax is valid, the query results are returned.
However, suppose there is a Cypher syntax error.
In that case, we do a single follow-up to GPT-4, provide the generated Cypher statement it constructed in the previous call, and include the error from the Neo4j database. GPT-4 is quite good at fixing a Cypher statement when provided with the error.
The self-healing Cypher flow was inspired by others who have used similar flows for Python and other code. However, I have limited the follow-up Cypher healing to only a single iteration. If the follow-up doesn’t provide a valid Cypher statement, the function returns the “Invalid Cypher syntax response.”
