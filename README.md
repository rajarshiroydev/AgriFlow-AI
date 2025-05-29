# <span style="color: #2F5233;">AgriFlow</span><span style="color: #6A994E;">.ai</span> - Syngenta AI Agent Hackathon

## Table of Contents

1.  [Project Overview](#project-overview)
2.  [Features](#features)
3.  [Tech Stack](#tech-stack)
4.  [Setup and Installation](#setup-and-installation)
    - [Prerequisites](#prerequisites)
    - [Step-by-Step Instructions](#step-by-step-instructions)
5.  [Usage](#usage)
6.  [Sample Questions to Test Access Control](#sample-questions-to-test-access-control)
7.  [Stopping the Application](#stopping-the-application)
8.  [Troubleshooting](#troubleshooting)

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
- **Interactive UI:** A React-based chat interface for user interaction, including features like SQL display formatting, syntax highlighting, copy-to-clipboard, and chat history management with rename/delete capabilities.
- **Custom LLM & Embedding Integration:** Utilizes a specific hackathon API endpoint for all Large Language Model (Claude 3.5 Sonnet) and Embedding (Amazon Titan) calls.

## Tech Stack

- **Backend:** Python, FastAPI, LangChain
- **LLM:** Claude 3.5 Sonnet (via custom Hackathon API)
- **Embeddings:** Amazon Titan (via custom Hackathon API)
- **Vector Store:** ChromaDB
- **Database:** PostgreSQL
- **Task Queue:** RabbitMQ, Redis (Primarily for Celery, if full async tasks are implemented beyond core chat)
- **Frontend:** React.js
- **Containerization:** Docker, Docker Compose

## Setup and Installation

Follow these steps to set up and run the AgriFlow.ai application locally using Docker.

### Prerequisites

- **Git:** [Install Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)
- **Docker & Docker Compose:** [Install Docker Desktop](https://www.docker.com/products/docker-desktop/) (which includes Docker Compose). Ensure Docker is running.
- **Node.js & npm (or yarn):** Required to run the React frontend development server. [Install Node.js and npm](https://nodejs.org/).

### Step-by-Step Instructions

1.  **Clone the Repository:**

    ```bash
    git clone https://github.com/soumyadeep-git/AgriFlow-AI.git
    cd backend/
    ```

2.  **Configure Environment Variables (`.env`):**
    Navigate to the backend directory of the cloned project. You should find a `.env` file.
    This file contains crucial settings, including API keys. **You will need to add your Syngenta Hackathon API Key.**

    Open the `.env` file. It should look similar to this (especially the API key part):

    ```env
    # ... other variables like DATABASE_URL, CELERY_BROKER_URL etc. ...

    # Add your LLM API Keys here
    #OPENAI_API_KEY="sk-..."

    SYNGENTA_HACKATHON_API_KEY="your-api-key-here"
    
    # ... other variables like VECTOR_STORE_PATH ...
    ```

    - **Replace `"your-api-key-here"` with the actual `SYNGENTA_HACKATHON_API_KEY` provided for the hackathon.**
    - Ensure all other URLs (DATABASE_URL, CELERY_BROKER_URL, CELERY_RESULT_BACKEND) are configured to use Docker service names as hostnames (e.g., `postgres_db`, `rabbitmq`, `redis`). The provided `.env` should already have these if it was committed.

3.  **Build and Start Backend Docker Containers:**
    Ensure that you are on the backend directory:

    ```bash
       docker-compose up --build -d
    ```

    - This command builds the Docker images for backend services and starts them in detached mode.
    - Wait for services like `postgres_db`, `rabbitmq`, `redis`, and `app` (FastAPI) to initialize. Check status with `docker-compose ps`.

4.  **Run Data Processing Scripts (Inside Docker):**
    Execute these commands one after the other from the project root directory. Wait for each to complete.

    **4.1. Before running these commands download the .csv file from https://www.kaggle.com/datasets/saicharankomati/dataco-supply-chain-dataset and keep it in backend/data/raw (just outside the dataco-global-policy-dataset folder)**

    - **a. Load SQL Data into PostgreSQL:**

      ```bash
      docker-compose exec app python scripts/load_sql_data.py
      ```

    - **b. Ingest PDF Documents into Vector Store:**
      ```bash
      docker-compose exec app python scripts/ingest_documents.py
      ```
      _(This script processes PDFs and generates embeddings. **This step can take several minutes.** Please be patient and monitor the console output for completion or errors.)_

    - **c. You can change the logs of the app if you want to(Optional):**
      ```bash
      docker-compose logs -f app
      ```
      _(This script processes PDFs and generates embeddings. **This step can take several minutes.** Please be patient and monitor the console output for completion or errors.)_
      
      

6.  **Run the Frontend Application:**
    You will need two terminals open simultaneously for this step and the next.

    - **Terminal 1 (Backend - Already Running):** Your Docker containers (FastAPI, database, etc.) should be running from Step 3. You can monitor their logs with `docker-compose logs -f app`.

    - **Terminal 2 (Frontend - React Development Server):**
      1.  Navigate to the frontend directory:
          ```bash
          cd frontend
          ```
      2.  Install dependencies (if not already done, or if `package-lock.json` changed):
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
      4.  This will typically open the application automatically in your default web browser at `http://localhost:3000`. If not, manually open it.

## Usage

1.  Once the frontend is running at `http://localhost:3000`, you can interact with the AgriFlow.ai assistant.
2.  The initial landing page presents the logo and a prompt. Type your query to begin.
3.  The interface will transition to a chat view with a sidebar for:
    - Starting a "New Chat".
    - Selecting a "Simulated User Profile" (Guest, Analyst US, Manager EMEA, Admin) to test access control. Changing profiles starts a new session.
    - Viewing and loading past chat sessions (with options to rename/delete).
4.  Explore by asking questions about policies or supply chain data.

## Sample Questions to Test Access Control

- **As "Guest (Global)":**
  - "What is our company policy on data privacy?" (Should be allowed)
  - "What is the total sales amount for all orders?" (Should be denied)
- **As "Analyst (US)":**
  - "What is the total sales amount?" (Allowed, filtered to US data)
  - "What is the total sales in EMEA?" (Denied or "data not available")
  - "What is the profit margin for product X?" (Denied - no financial metrics permission)
- **As "Manager (EMEA)":**
  - "Show me profit margins for all products." (Allowed, filtered to EMEA data)
- **As "Administrator (Global)":**
  - This user profile has `admin_override_all` and broad permissions. Most queries, including cross-regional ones and those involving sensitive data types (like financials), should be **GRANTED**. For example: "What are the total sales in US and EMEA combined?" or "List all products and their profit margins globally."

_(List other complex/hybrid sample questions here)_

## Stopping the Application

1.  **To stop backend Docker containers:**
    In the terminal where you ran `docker-compose up` (or any terminal in the project root):
    ```bash
    docker-compose down
    ```
2.  **To stop the React development server:**
    In Terminal 2 (where `npm start` or `yarn start` is running), press `Ctrl+C`.

## Troubleshooting

- **`no configuration file provided: not found` (for `docker-compose`):** Ensure you are in the project's root directory where `docker-compose.yml` is located when running `docker-compose` commands.
- **Port Conflicts:** If ports (e.g., 8000, 3000, 5432) are in use, services might fail to start. Check terminal output for errors.
- **API Key Errors:** Double-check `SYNGENTA_HACKATHON_API_KEY` in `.env`. Backend logs (`docker-compose logs -f app`) will show API call issues.
- **`ingest_documents.py` "Stuck":** This script takes time for embeddings. Be patient. If it errors, check its output.
