# AgriFlow.ai - Syngenta AI Agent Hackathon

AgriFlow.ai is an intelligent agent designed to answer queries by leveraging both policy documents (PDFs) and a structured PostgreSQL database. It features natural language understanding, hybrid query orchestration, role-based access control, and conversational memory.

**Live Demo Link:** [Insert Link to Deployed App if available, e.g., Streamlit Cloud, Vercel, Netlify] (Optional)
**Video Presentation Link:** [Insert Link to Your Video Presentation]

## Table of Contents

1.  [Project Overview](#project-overview)
2.  [Features](#features)
3.  [Technical Architecture](#technical-architecture)
4.  [Prerequisites](#prerequisites)
5.  [Setup and Installation](#setup-and-installation)
    - [Cloning the Repository](#cloning-the-repository)
    - [Environment Configuration](#environment-configuration)
    - [Building and Running with Docker Compose](#building-and-running-with-docker-compose)
    - [Accessing the Application](#accessing-the-application)
6.  [Running Services Individually (Alternative for Development)](#running-services-individually-alternative-for-development)
    - [Backend API](#backend-api)
    - [Celery Worker (if applicable)](#celery-worker-if-applicable)
    - [Frontend (React)](#frontend-react)
7.  [Usage](#usage)
    - [Interacting with the Chat Interface](#interacting-with-the-chat-interface)
    - [Simulated User Profiles for Access Control](#simulated-user-profiles-for-access-control)
    - [Sample Queries](#sample-queries)
8.  [Testing (Backend)](#testing-backend)
9.  [Directory Structure](#directory-structure)
10. [Team](#team)

---

## 1. Project Overview

AgriFlow.ai allows users to ask complex questions that may require information from company policy documents (e.g., PDFs on inventory management, sustainability) and transactional data stored in a PostgreSQL database (e.g., sales, supply chain transactions). The system intelligently determines the data sources needed, retrieves information, and synthesizes a comprehensive answer.

## 2. Features

- **Natural Language Querying:** Understands user questions in plain English.
- **Document Q&A (RAG):** Answers questions based on PDF policy documents using Retrieval Augmented Generation.
- **Database Q&A (Text-to-SQL):** Converts natural language to SQL queries to fetch data from PostgreSQL.
- **Hybrid Query Orchestration:** Decomposes complex queries that require both document and database lookups, refines sub-queries, and synthesizes final answers.
- **Conversational Memory:** Remembers the context of recent interactions for natural follow-up questions.
- **Role-Based Access Control (RBAC) & Geographic Restrictions (Simulated):**
  - Filters data and restricts access based on simulated user roles and regional permissions.
  - Demonstrates how data governance can be applied.
- **Intuitive React Frontend:** A user-friendly chat interface for interacting with the agent.
- **Dockerized Deployment:** Easy setup and consistent environment using Docker Compose.
- **Custom LLM & Embedding API Integration:** Utilizes the hackathon-provided API for all LLM (Claude 3.5 Sonnet) and embedding (Amazon Titan) calls.

## 3. Technical Architecture

- **Frontend:** React (using Vite or Create React App)
- **Backend:** FastAPI (Python)
- **Database (Structured Data):** PostgreSQL
- **Vector Store (Document Embeddings):** ChromaDB
- **LLM & Embeddings:** Custom API endpoint provided by the hackathon (interfaced via LangChain custom classes).
  - LLM Model: Claude 3.5 Sonnet (or Haiku for certain tasks)
  - Embedding Model: Amazon Titan Embedding v2
- **Task Queue (Optional, if used):** Celery with RabbitMQ broker and Redis backend.
- **Containerization:** Docker & Docker Compose

_(Consider embedding a simple architecture diagram image here if you have one)_
`![Architecture Diagram](path/to/your/architecture_diagram.png)`

## 4. Prerequisites

- **Git:** For cloning the repository.
- **Docker Desktop:** (or Docker Engine + Docker Compose CLI plugin) installed and running. Version X.Y.Z or higher recommended.
- **A modern web browser:** Chrome, Firefox, Edge, Safari.
- **Terminal/Command Prompt:** For running commands.
- **(Optional, for individual service development):**
  - Python 3.10+ and `pip`
  - Node.js (e.g., v18+) and `npm` (or `yarn`)

## 5. Setup and Installation

These instructions assume you are setting up the project to run via Docker Compose, which handles all services.

### Cloning the Repository

1.  Open your terminal.
2.  Clone the repository (ensure you are on the correct `backend` branch if that's where the complete code resides):
    ```bash
    git clone <your-github-repository-url>
    cd <repository-folder-name>
    git checkout backend # If your code is on the 'backend' branch
    ```

### Environment Configuration

The application requires API keys and other configurations to be set up in an environment file.

1.  **Locate the example environment file:** In the root of the project, you should find a file named `.env.example`.
2.  **Create your own environment file:** Copy `.env.example` to a new file named `.env` in the same root directory:
    ```bash
    cp .env.example .env
    ```
3.  **Edit `.env`:** Open the `.env` file in a text editor and fill in the required values, especially:

    - `SYNGENTA_HACKATHON_API_KEY`: Your unique API key for the hackathon's LLM/Embedding service.
    - `SYNGENTA_HACKATHON_API_BASE_URL`: The base URL for the hackathon's API service.
    - Other variables like `DATABASE_URL`, `CELERY_BROKER_URL`, etc., are typically pre-configured in your `docker-compose.yml` to connect to other Docker services by their service names (e.g., `postgres_db`, `rabbitmq`). Double-check these if you've made custom changes.

    **Example `.env` structure (ensure values match your setup):**

    ```env
    ENVIRONMENT=development
    DATABASE_URL=postgresql://syngenta_user:syngenta_password@postgres_db:5432/syngenta_supplychain_db
    CELERY_BROKER_URL=amqp://guest:guest@rabbitmq:5672//
    CELERY_RESULT_BACKEND=redis://redis:6379/0
    SYNGENTA_HACKATHON_API_KEY=your_actual_api_key_here
    SYNGENTA_HACKATHON_API_BASE_URL=your_hackathon_api_base_url_here
    VECTOR_STORE_PATH=data/processed/vector_store # Path relative to project root for ChromaDB
    # OPENAI_API_KEY= (Optional, if you were using OpenAI directly for anything)
    ```

### Building and Running with Docker Compose

This is the recommended way to run the entire application stack. You will typically need **one terminal window** for this.

1.  **Navigate to the project root directory** (where `docker-compose.yml` is located) in your terminal.

2.  **Build and Start Services:**
    Run the following command:

    ```bash
    docker-compose up --build -d
    ```

    - `--build`: Forces Docker to rebuild the images if there are changes to Dockerfiles or source code included in the image.
    - `-d`: Runs the containers in detached mode (in the background).

    This command will:

    - Pull necessary base images (PostgreSQL, RabbitMQ, Redis).
    - Build your custom images for the FastAPI backend (`app` service) and Celery worker (`worker` service), which also includes the React frontend build if it's served by FastAPI or built into the `app` image.
    - Start all defined services.

3.  **Initial Data Loading & Document Ingestion (Important First-Time Setup):**
    The first time you run the application, the database needs to be populated and policy documents need to be ingested into the vector store. These are typically handled by scripts.

    - **Check Logs:** After `docker-compose up` finishes, monitor the logs for any script execution or wait for services to be healthy.
      ```bash
      docker-compose logs -f app
      # And in another terminal if needed:
      # docker-compose logs -f worker
      ```
    - **Run Ingestion Scripts (if not automated in Docker entrypoint/command):**
      You may need to execute scripts _inside_ the running `app` or `worker` container to load data.
      To run a script inside the `app` container (replace `syngenta_app` with your app service name if different):

      ```bash
      # Example: Load SQL data
      docker-compose exec app python scripts/load_sql_data.py

      # Example: Ingest documents into vector store
      docker-compose exec app python scripts/ingest_documents.py
      ```

      _Look for specific instructions in your project for these scripts or if they run automatically._

    - **Wait for Services:** It might take a few moments for all services (especially the database) to initialize fully. Check health status with `docker-compose ps`.

### Accessing the Application

- **React Frontend (Chat Interface):** Open your web browser and navigate to:
  `http://localhost:3000` (if your React app is served by its own dev server mapped to port 3000 from Docker, common setup).
  OR
  `http://localhost:8000` (if your FastAPI app serves the built React static files, and port 8000 is mapped).
  _(Adjust the port based on your `docker-compose.yml` port mappings for the frontend/app service)._

- **FastAPI Backend API Docs (Swagger UI):**
  `http://localhost:8000/docs` (if port 8000 is mapped to your FastAPI `app` service).

- **RabbitMQ Management (if used):**
  `http://localhost:15672` (Username: `guest`, Password: `guest`)

---

## 6. Running Services Individually (Alternative for Development)

This section is for developers who want to run services outside of Docker, typically for easier debugging or faster frontend hot-reloading. **Ensure Docker Compose services are stopped (`docker-compose down`) to avoid port conflicts.**

You'll likely need **multiple terminal windows** for this approach.

- **Terminal 1: Dockerized Infrastructure (DB, RabbitMQ, Redis)**
  If you still want to use Docker for backing services:
  ```bash
  docker-compose up -d postgres_db rabbitmq redis
  # (Or your specific service names for these)
  ```
  Ensure your local `.env` file has `DATABASE_URL`, `CELERY_BROKER_URL`, etc., pointing to `localhost` and the correct ports (e.g., `localhost:5432` for PostgreSQL).

### Backend API (FastAPI)

1.  **Navigate to project root.**
2.  **Create/Activate Python Virtual Environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # Linux/macOS
    # venv\Scripts\activate    # Windows
    ```
3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Run FastAPI App (from project root):**
    ```bash
    python main.py run-api --reload
    # Or directly with uvicorn:
    # uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    ```
    The API will typically be available at `http://localhost:8000`.

### Celery Worker (if applicable)

1.  **Ensure RabbitMQ and Redis are running** (either via Docker or locally).
2.  **Open a new terminal.**
3.  **Navigate to project root and activate virtual environment.**
4.  **Run Celery Worker (from project root):**
    ```bash
    python main.py run-worker
    # Or directly:
    # celery -A tasks.celery_app worker -l info -Q celery,default,supply_chain_tasks
    ```

### Frontend (React)

1.  **Navigate to your frontend directory** (e.g., `cd frontend`).
2.  **Install Dependencies:**
    ```bash
    npm install
    # or
    # yarn install
    ```
3.  **Start Frontend Development Server:**
    ```bash
    npm start
    # or
    # yarn start
    ```
    The React app will typically be available at `http://localhost:3000`. Ensure its `API_URL` (in `App.js` or an environment variable like `REACT_APP_API_URL`) points to your locally running FastAPI backend (e.g., `http://localhost:8000/api/v1/chat`).

---

## 7. Usage

### Interacting with the Chat Interface

Once the application is running, open the React frontend in your browser.

- Type your questions into the input bar at the bottom.
- The agent will process your query and display the answer, along with any sources (for document queries) or generated SQL (for database queries).
- The interface supports conversational follow-ups.
- You can manage chat history (rename, delete, load) using the options in the sidebar.

### Simulated User Profiles for Access Control

The sidebar includes a dropdown menu to "Act as" different simulated users:

- **Guest (Global):** Limited access, primarily to public policies. Cannot query most database details.
- **Analyst (US):** Can access US-specific sales and inventory data. Cannot view financial metrics or data from other regions.
- **Manager (EMEA):** Can access EMEA sales, inventory, and financial metrics. Cannot view data from other regions.
- **Administrator (Global):** Full access to all data, all regions, and all policies.

Select a user profile and ask queries to observe how access control and regional filtering are applied.

### Sample Queries

Try these queries with different user profiles:

- "What is the total sales amount for all orders?"
- "What is our company's definition of slow-moving inventory according to the Inventory Management policy?"
- (As Analyst US) "What were the total sales last quarter?" (Should be US only)
- (As Analyst US) "What were the total sales in EMEA last quarter?" (Should be denied/no data)
- (As Admin) "Which inventory items qualify as 'no-movers' according to our policy, and what is their total current value?"
- "Are we using optimal shipping modes for high-value international orders per our logistics policy?"

---

## 8. Testing (Backend)

The backend includes unit and integration tests. To run them (example):

1.  Ensure your development environment is set up (or run inside the Docker container).
2.  Navigate to the project root.
3.  Run pytest:
    ```bash
    # (Activate venv if not in Docker)
    pytest
    ```
    _(Adjust if your test setup is different)_

---

## 9. Directory Structure
