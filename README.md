# AgriFlow.ai - Syngenta AI Agent Hackathon

## Project Overview

AgriFlow.ai is an intelligent AI agent designed for the Syngenta Hackathon. It empowers users to query company policy documents (PDFs) and a structured supply chain database using natural language. The agent can handle complex hybrid queries that require information from both sources, providing synthesized and context-aware answers. Key features include robust data ingestion, advanced query decomposition, Role-Based Access Control (RBAC), geographic data filtering, and a conversational memory for follow-up questions.

## Features

- **Natural Language Querying:** Ask questions in plain English.
- **Document Q&A (RAG):** Answers questions based on PDF policy documents.
- **Database Q&A (Text-to-SQL):** Converts natural language to SQL queries to fetch data from a PostgreSQL database.
- **Hybrid Query Orchestration:** Intelligently decomposes queries that require both document and database lookups, refines sub-questions, and synthesizes comprehensive answers.
- **Conversational Memory:** Remembers recent interactions for context-aware follow-up questions.
- **Access Control & Governance:**
  - Simulated Role-Based Access Control (RBAC) to restrict data access based on user roles.
  - Geographic data filtering based on user profiles.
  - Audit logging for access attempts.
- **Interactive UI:** A React-based chat interface for user interaction, including features like SQL display formatting, copy-to-clipboard, and chat history management.
- **Custom LLM & Embedding Integration:** Utilizes a specific hackathon API endpoint for all Large Language Model (Claude 3.5 Sonnet) and Embedding (Amazon Titan) calls.

## Tech Stack

- **Backend:** Python, FastAPI, LangChain
- **LLM:** Claude 3.5 Sonnet (via custom Hackathon API)
- **Embeddings:** Amazon Titan (via custom Hackathon API)
- **Vector Store:** ChromaDB
- **Database:** PostgreSQL
- **Task Queue (Optional - if Celery is actively used beyond initial setup):** Celery, RabbitMQ, Redis
- **Frontend:** React.js
- **Containerization:** Docker, Docker Compose

## Project Structure (Key Directories)

## Setup and Installation

Follow these steps to set up and run the AgriFlow.ai application locally using Docker.

**Prerequisites:**

- **Git:** [Install Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)
- **Docker & Docker Compose:** [Install Docker Desktop](https://www.docker.com/products/docker-desktop/) (which includes Docker Compose). Ensure Docker is running.

**Instructions:**

1.  **Clone the Repository:**

    ```bash
    git clone <your_repository_url>
    cd <repository_folder_name>
    ```

2.  **Create Environment File (`.env`):**
    In the root directory of the project, create a file named `.env`. Copy the contents from `.env.example` (if provided) or use the template below, filling in your actual credentials and paths if necessary.

    **Example `.env` content:**

    ```env
    ENVIRONMENT=development

    # Docker service names are used as hostnames
    DATABASE_URL=postgresql://syngenta_user:syngenta_password@postgres_db:5432/syngenta_supplychain_db
    CELERY_BROKER_URL=amqp://guest:guest@rabbitmq:5672/
    CELERY_RESULT_BACKEND=redis://redis:6379/0

    # Syngenta Hackathon API Credentials
    SYNGENTA_HACKATHON_API_KEY=YOUR_ACTUAL_HACKATHON_API_KEY
    SYNGENTA_HACKATHON_API_BASE_URL=https://quchnti6xu7yzw7hfzt5yjqtvi0kafsq.lambda-url.eu-central-1.on.aws/ # Or your specific endpoint

    # Path for the vector store (relative to project root when scripts run inside Docker container's /app mount)
    VECTOR_STORE_PATH=data/processed/vector_store
    ```

    - **Important:** Replace `YOUR_ACTUAL_HACKATHON_API_KEY` with the API key provided for the hackathon.

3.  **Build and Start Docker Containers:**
    From the project root directory (where `docker-compose.yml` is located), run:

    ```bash
    docker-compose up --build -d
    ```

    - `--build`: Builds the Docker images for your application services.
    - `-d`: Runs containers in detached mode (in the background).
    - This command will start the FastAPI backend, PostgreSQL database, RabbitMQ, Redis, and the Celery worker (if configured).
    - Wait a minute or two for all services to initialize, especially the database. You can check the status with `docker-compose ps`.

4.  **Run Data Processing Scripts:**
    These scripts need to be run once to load data into the PostgreSQL database and create the vector store from PDF documents. Execute them inside the running `app` container:

    - **a. Load SQL Data:**

      ```bash
      docker-compose exec app python scripts/load_sql_data.py
      ```

      _(Wait for this to complete. It will populate the `supply_chain_transactions` table.)_

    - **b. Ingest Documents for Vector Store:**
      ```bash
      docker-compose exec app python scripts/ingest_documents.py
      ```
      _(This script will process PDFs, generate embeddings via the hackathon API, and create a ChromaDB vector store. **This step can take several minutes** depending on the number of documents and API responsiveness. Please be patient.)_

5.  **Access the Application:**

    - **Frontend (React App):**
      The React frontend is typically run with its own development server.

      1.  Navigate to the frontend directory:
          ```bash
          cd frontend
          ```
      2.  Install dependencies (if you haven't already):
          ```bash
          npm install
          # OR
          # yarn install
          ```
      3.  Start the React development server:
          ```bash
          npm start
          # OR
          # yarn start
          ```
      4.  Open your browser and go to `http://localhost:3000` (or the port indicated by the React dev server). The React app is configured to communicate with the backend API running on port 8000.

    - **Backend API Docs (Optional):**
      The FastAPI backend documentation (Swagger UI) can be accessed at `http://localhost:8000/docs`. The main chat endpoint is `POST /api/v1/chat`.

## Usage

1.  Once the frontend is running at `http://localhost:3000`, you can start interacting with the AgriFlow.ai assistant.
2.  On the initial landing page, type your query into the input bar.
3.  After your first query, the interface will transition to the chat view, showing a sidebar with:
    - A "New Chat" button.
    - A user profile selector (to simulate different roles like "Guest", "Analyst US", "Manager EMEA", "Admin"). Changing the profile will start a new chat session reflecting the selected user's access rights.
    - Chat history, categorized by "Today", "Yesterday", etc. You can click on past chats to load them.
    - Options to rename or delete saved chats.
4.  Ask questions related to Syngenta policies or supply chain data. Try the [Sample Questions](#sample-questions) below for inspiration.

## Sample Questions to Test Access Control

- **As "Guest (Global)":**
  - "What is our company's policy on data privacy?" (Should be allowed)
  - "What is the total sales amount for all orders?" (Should be denied)
- **As "Analyst (US)":**
  - "What is the total sales amount?" (Should be allowed and filtered to US data)
  - "What is the total sales in EMEA?" (Should be denied or state data not available)
  - "What is the profit margin for product X?" (Should be denied - no financial metrics permission)
- **As "Manager (EMEA)":**
  - "Show me profit margins for all products." (Should be allowed and filtered to EMEA data)
- **As "Administrator (Global)":**
  - "What are the total sales in US and EMEA combined?" (Should be allowed)
  - "Which products that are classified as 'hazardous materials' according to our HSE policy are currently being stored in facilities not certified for such materials?" (Complex hybrid query, should be allowed)

_(You can list more of your sample questions here)_

## Stopping the Application

To stop all running Docker containers:

```bash
docker-compose down
```
