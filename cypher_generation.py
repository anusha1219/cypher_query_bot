import os
from neo4j import GraphDatabase
from openai import AzureOpenAI
from neo4j.exceptions import CypherSyntaxError
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv


# Load environment variables from .env file
load_dotenv()

# Get environment variables
uri = os.getenv("neo_url")
user = os.getenv("neo_user")
password = os.getenv("neo_password")
ad_token_path = os.getenv("azure_default_adtoken")
azure_endpoint = os.getenv("azure_endpoint")
openai_api_key = os.getenv("azure_api_key")
openai_api_version = os.getenv("azure_api_version")

# Define your queries
node_properties_query = """
CALL apoc.meta.data()
YIELD label, other, elementType, type, property
WHERE NOT type = "RELATIONSHIP" AND elementType = "node"
WITH label AS nodeLabels, collect(property) AS properties
RETURN {labels: nodeLabels, properties: properties} AS output

"""

rel_properties_query = """
CALL apoc.meta.data()
YIELD label, other, elementType, type, property
WHERE NOT type = "RELATIONSHIP" AND elementType = "relationship"
WITH label AS nodeLabels, collect(property) AS properties
RETURN {type: nodeLabels, properties: properties} AS output
"""

rel_query = """
CALL apoc.meta.data()
YIELD label, other, elementType, type, property
WHERE type = "RELATIONSHIP" AND elementType = "node"
RETURN {source: label, relationship: property, target: other} AS output
"""


def schema_text(node_props, rel_props, rels):
    return f"""
  This is the schema representation of the Neo4j database.
  Node properties are the following:
  {node_props}
  Relationship properties are the following:
  {rel_props}
  Relationship point from source to target nodes
  {rels}
  Make sure to respect relationship types do not use relationship direction
  """

class Neo4jGPTQuery:
    def __init__(self, url, user, password):
        driver_config = {
        "encrypted": True,
        "trust": "TRUST_ALL_CERTIFICATES"
        }
        self.driver = GraphDatabase.driver(url, auth=(user, password),trust="TRUST_ALL_CERTIFICATES",encrypted=True,database="db_name")
        #AzureOpenAI.api_key = openai_api_key
        # construct schema
        self.schema = self.generate_schema()
        retry=True


    def generate_schema(self):
        node_props = self.query_database(node_properties_query)
        rel_props = self.query_database(rel_properties_query)
        rels = self.query_database(rel_query)
        return schema_text(node_props, rel_props, rels)

    def refresh_schema(self):
        self.schema = self.generate_schema()

    def get_system_message(self):
        return f"""
        Task: Generate Cypher queries to query a Neo4j graph database based on the provided schema definition.
        Instructions:
        Use only the provided relationship types and properties.
        Do not use any other relationship types or properties that are not provided.
        If you cannot generate a Cypher statement based on the provided schema, explain the reason to the user.
        Schema:
        {self.schema}

        Note: Do not include any explanations or apologies in your responses.
        """

    def query_database(self, neo4j_query, params={}):
        with self.driver.session() as session:
            result = session.run(neo4j_query, params)
            output = [r.values() for r in result]
            output.insert(0, result.keys())
            print(output)
            return output

    def construct_cypher(self, question, history=None):
        messages = [
            {"role": "system", "content": self.get_system_message()},
            {"role": "user", "content": question},
        ]
        # Used for Cypher healing flows
        if history:
            messages.extend(history)
        token_provider = get_bearer_token_provider(
                            DefaultAzureCredential(), ad_token_path
                        )
        
        client = AzureOpenAI(
        azure_endpoint = azure_endpoint,
        azure_ad_token_provider=token_provider,
        api_version = openai_api_version
        )
        completions = client.chat.completions.create(
        model = "deployment_name",
        messages = messages,
        temperature=0,
        max_tokens=1000,
        )
        return completions.choices[0].message.content

    def run(self, question, history=None, retry=True):
        # Construct Cypher statement
        cypher = self.construct_cypher(question, history)
        #print(cypher)
        try:
            cypher= cypher.strip('```').removeprefix("cypher")
            print(cypher)
            return self.query_database(cypher)
        # Self-healing flow
        except CypherSyntaxError as e:
            print(e)
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

if __name__ == "__main__":
    gds_db = Neo4jGPTQuery(
        url = uri,
        user =user,
        password = password
    )

    gds_db.run("""
    Give the query related to your graph schema
    """)

