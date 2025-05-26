import os
import logging
from typing import Any, Dict, List

from sqlalchemy import create_engine
from langchain_community.utilities import SQLDatabase
from langchain.agents import create_sql_agent, AgentExecutor # AgentExecutor is returned by create_sql_agent
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from crewai import Agent as CrewAIAgent, Task as CrewAITask, Crew, Process # Alias to avoid name clash
from crewai.tools import tool # For creating CrewAI tools

from core.hackathon_llms import SyngentaHackathonLLM
from config.settings import settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- LLM for SQL Agent's SQL Generation ---
sql_generation_llm = None
try:
    sql_generation_llm = SyngentaHackathonLLM(
        model_id="claude-3.5-sonnet", temperature=0.1, max_tokens=2000
    )
    logger.info("LLM (Claude 3.5 Sonnet) initialized for SQL Generation.")
except Exception as e:
    logger.error(f"Failed to initialize sql_generation_llm: {e}", exc_info=True)

# --- Database Connection ---
db_langchain_wrapper = None # Renamed from 'db' for clarity
if settings.DATABASE_URL:
    try:
        db_engine = create_engine(str(settings.DATABASE_URL))
        db_langchain_wrapper = SQLDatabase(db_engine) # This is LangChain's SQLDatabase
        logger.info(f"LangChain SQLDatabase initialized. Usable tables: {db_langchain_wrapper.get_usable_table_names()}")
    except Exception as e:
        logger.error(f"Failed to create SQLDatabase wrapper: {e}", exc_info=True)
        db_langchain_wrapper = None
else:
    logger.error("DATABASE_URL not found in settings.")

# --- LangChain SQL Agent Executor (This is a powerful tool itself) ---
langchain_sql_agent_executor: Optional[AgentExecutor] = None # Type hint for clarity
if db_langchain_wrapper and sql_generation_llm:
    try:
        sql_toolkit = SQLDatabaseToolkit(db=db_langchain_wrapper, llm=sql_generation_llm)
        langchain_sql_agent_executor = create_sql_agent(
            llm=sql_generation_llm,
            toolkit=sql_toolkit,
            verbose=True, # Shows LangChain SQL agent's thoughts
            agent_type="openai-tools", # Or another suitable agent type
            handle_parsing_errors=True,
            # You can add a prompt prefix here to give general instructions to the SQL agent
            # prefix="You are an agent designed to interact with a supply chain transactions database..."
        )
        logger.info("LangChain SQL Agent Executor created successfully.")
    except Exception as e:
        logger.error(f"Failed to create LangChain SQL Agent Executor: {e}", exc_info=True)
        langchain_sql_agent_executor = None

# --- CrewAI Tool that uses the LangChain SQL Agent Executor ---
@tool("DatabaseQueryTool")
def database_query_tool(natural_language_query: str) -> str:
    """
    Use this tool to answer questions by querying the supply chain database.
    Input should be a natural language question that requires data from the database.
    The tool will convert this question to SQL, execute it, and return the answer.
    Example questions: 'What is the total sales?', 'Which region had the most orders?'.
    """
    logger.info(f"CrewAI Tool 'DatabaseQueryTool' called with NLQ: '{natural_language_query}'")
    if not langchain_sql_agent_executor:
        return "Error: The underlying SQL querying agent is not available."
    try:
        # The LangChain SQL agent executor takes a dictionary input
        response = langchain_sql_agent_executor.invoke({"input": natural_language_query})
        answer = response.get("output", "Could not get a definitive answer from the database.")
        logger.info(f"DatabaseQueryTool response: {answer}")
        return answer
    except Exception as e:
        logger.error(f"Error executing DatabaseQueryTool for query '{natural_language_query}': {e}", exc_info=True)
        return f"Error when querying database: {str(e)}"

# --- CrewAI Agent for Database Queries ---
# This agent will use the reasoning_llm for its own thought process
# and the DatabaseQueryTool to interact with the DB.
reasoning_llm_for_crewai_sql_agent = None
try:
    reasoning_llm_for_crewai_sql_agent = SyngentaHackathonLLM(
        model_id="claude-3.5-sonnet", # Sonnet for good reasoning to use the tool
        temperature=0.5,
        max_tokens=2000
    )
    logger.info("Reasoning LLM (Claude 3.5 Sonnet) initialized for CrewAI SQL Agent.")
except Exception as e:
    logger.error(f"Failed to initialize reasoning_llm_for_crewai_sql_agent: {e}", exc_info=True)

crewai_sql_query_agent = None
if reasoning_llm_for_crewai_sql_agent and database_query_tool:
    crewai_sql_query_agent = CrewAIAgent(
        role="SQL Database Query Specialist",
        goal="Understand natural language questions and use the DatabaseQueryTool to find answers from the supply chain database. Provide clear and concise answers based on the tool's output.",
        backstory="You are an expert at translating business questions into actionable database queries using a specialized tool. You interpret the tool's results to provide user-friendly answers.",
        verbose=True, # Shows CrewAI agent's thoughts
        allow_delegation=False,
        llm=reasoning_llm_for_crewai_sql_agent,
        tools=[database_query_tool]
    )
    logger.info("CrewAI SQL Query Agent created.")
else:
    logger.warning("CrewAI SQL Query Agent not created due to missing LLM or Tool.")

# --- Wrapper Function to run the CrewAI SQL Agent ---
def run_crewai_sql_query(user_query: str) -> Dict[str, Any]:
    """
    Takes a natural language user query, uses the CrewAI SQL Agent to get an answer.
    """
    if not crewai_sql_query_agent:
        return {"answer": "Error: CrewAI SQL Query Agent is not available.", "error": "Agent not initialized"}

    logger.info(f"Processing query via CrewAI SQL Agent: '{user_query}'")

    task = CrewAITask(
        description=(
            f"Answer the following user question using the 'DatabaseQueryTool':\n"
            f"USER QUESTION: \"{user_query}\"\n\n"
            f"You must use the 'DatabaseQueryTool'. Pass the exact USER QUESTION to the tool."
            f"Your final answer should be the direct response from the tool."
        ),
        expected_output="The answer to the user's question, obtained by using the DatabaseQueryTool.",
        agent=crewai_sql_query_agent,
        tools=[database_query_tool] # Explicitly pass tool to task as well
    )

    # For a single agent, single task crew
    query_crew = Crew(
        agents=[crewai_sql_query_agent],
        tasks=[task],
        process=Process.sequential,
        verbose=2 # Higher verbosity for Crew
    )

    try:
        crew_result = query_crew.kickoff()
        # The 'raw' attribute might not always be present or be the final answer structure
        # It's often better to rely on the last task's output if clearly defined.
        # For a single task, crew_result might be the string output directly.
        
        answer = "No definitive answer from CrewAI SQL agent."
        if isinstance(crew_result, str):
            answer = crew_result
        elif hasattr(crew_result, 'raw') and crew_result.raw:
            answer = crew_result.raw
        elif isinstance(crew_result, dict) and 'output' in crew_result: # LangChain agent like output
            answer = crew_result['output']

        logger.info(f"CrewAI SQL Agent final answer: {answer}")
        # Generated SQL is harder to get from CrewAI agent unless tool returns it or it's in verbose logs
        return {"answer": answer, "generated_sql": "Check verbose LangChain SQL Agent logs for SQL", "error": None}
    except Exception as e:
        logger.error(f"Error during CrewAI SQL Agent execution for query '{user_query}': {e}", exc_info=True)
        return {"answer": f"Error processing SQL query via CrewAI: {str(e)}", "generated_sql": None, "error": str(e)}

# --- Test block ---
if __name__ == '__main__':
    # ... (dotenv loading as before) ...

    if not langchain_sql_agent_executor: # Check if the LangChain agent is ready
        logger.critical("LangChain SQL Agent Executor NOT INITIALIZED. Cannot run direct tests.")
    else:
        logger.info("\n--- (A) TESTING LangChain SQL Agent DIRECTLY ---")
        direct_test_queries = [
            "What is the total sales amount for all orders?",
            "How many orders are there in the 'SUSPECTED_FRAUD' order status?",
            "List the first 3 customer first names from customer_city 'Caguas'",
        ]
        for query in direct_test_queries:
            logger.info(f"\n--- Direct LangChain SQL Agent Test: '{query}' ---")
            # Directly invoke the LangChain agent executor
            try:
                response = langchain_sql_agent_executor.invoke({"input": query})
                answer = response.get("output", "No output from direct invoke.")
                print(f"Query: {query}\nAnswer: {answer}\n---")
            except Exception as e:
                print(f"Query: {query}\nError: {e}\n---")
    
    logger.info("\n--- (B) TESTING CrewAI SQL Agent ---")
    if not crewai_sql_query_agent:
        logger.critical("CrewAI SQL Query Agent NOT INITIALIZED. Cannot run CrewAI tests.")
    else:
        crew_test_queries = [
            "What are the top 2 order regions by sales?",
            "count the number of late deliveries" # More natural language
        ]
        for query in crew_test_queries:
            logger.info(f"\n--- CrewAI SQL Agent Test: '{query}' ---")
            result = run_crewai_sql_query(query) # Call our wrapper for the CrewAI agent
            print(f"Query: {query}")
            print(f"Generated SQL (from logs): {result.get('generated_sql')}")
            print(f"Answer: {result.get('answer')}")
            if result.get('error'):
                print(f"Error: {result.get('error')}")
            print("-----------------------------\n")
    
    logger.info("--- SQL Query Agent tests finished ---")