# Ragnar

Ragnar is a Django-based RAG report generation project. It uses PostgreSQL for the main application database and a PostgreSQL database with `pgvector` support for vector storage.

## Prerequisites

- Git
- Python 3.11 or newer
- Docker
- PostgreSQL client tools are optional, but useful for checking databases manually

## Clone the Project

```bash
git clone https://github.com/exagenio/ragnar.git
cd ragnar_web
```

## Create and Activate a Virtual Environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

## Install Required Packages

This repository currently does not include a `requirements.txt`, so install the packages used by the project directly:

```bash
pip install django psycopg psycopg2-binary python-dotenv cryptography python-docx plotly pandas textstat sentence-transformers deepeval openevals langchain-core langchain-postgres langchain-google-vertexai langchain-google-genai langchain-ollama langchain-openrouter
```

After the dependencies are finalized, you can save them with:

```bash
pip freeze > requirements.txt
```

Future setup can then use:

```bash
pip install -r requirements.txt
```

## Main Project Database Setup

The Django app uses a normal PostgreSQL database for project data, users, reports, tasks, and generated content.

Run PostgreSQL with Docker:

```bash
docker run --name ragnar-postgres \
  -e POSTGRES_DB=rag_app_db \
  -e POSTGRES_USER=rag_user \
  -e POSTGRES_PASSWORD=strongpassword \
  -p 5432:5432 \
  -v ragnar_postgres_data:/var/lib/postgresql/data \
  -d postgres:16
```

Windows PowerShell single-line version:

```powershell
docker run --name ragnar-postgres -e POSTGRES_DB=rag_app_db -e POSTGRES_USER=rag_user -e POSTGRES_PASSWORD=strongpassword -p 5432:5432 -v ragnar_postgres_data:/var/lib/postgresql/data -d postgres:16
```

## Vector Database Setup

The vector database needs PostgreSQL with the `pgvector` extension. The project uses this database through `langchain-postgres`.

Run PostgreSQL with vector support:

```bash
docker run --name ragnar-vector-db-test \
  -e POSTGRES_DB=rag_vector_db \
  -e POSTGRES_USER=vector_user \
  -e POSTGRES_PASSWORD=vectorpassword \
  -p 5433:5432 \
  -v ragnar_vector_data:/var/lib/postgresql/data \
  -d pgvector/pgvector:pg16
```

Windows PowerShell single-line version:

```powershell
docker run --name ragnar-vector-db-test -e POSTGRES_DB=rag_vector_db -e POSTGRES_USER=vector_user -e POSTGRES_PASSWORD=vectorpassword -p 5433:5432 -v ragnar_vector_data:/var/lib/postgresql/data -d pgvector/pgvector:pg16
```

Enable the vector extension:

```bash
docker exec -it ragnar-vector-db psql -U vector_user -d rag_vector_db -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

## Vertex AI Setup Without API Keys

This project can use Vertex AI for LLM and embedding models through Google Cloud Application Default Credentials (ADC). With ADC, your local machine authenticates through Google Cloud credentials, so the Vertex AI libraries can access models without storing a Google API key in the project.

### 1. Create or Select a Google Cloud Project

1. Open the Google Cloud Console.
2. Use the project selector at the top of the dashboard.
3. Create a new project or select an existing project.
4. Make sure billing is enabled for the selected project.
5. Copy the project ID. You will use it as `VERTEX_AI_PROJECT`.

### 2. Enable the Vertex AI API

From the Google Cloud Console:

1. Go to **APIs & Services**.
2. Open **Library**.
3. Search for **Vertex AI API**.
4. Open the Vertex AI API page.
5. Click **Enable**.

Or enable it from the terminal:

```bash
gcloud services enable aiplatform.googleapis.com --project YOUR_PROJECT_ID
```

### 3. Configure IAM Permissions

The Google account you use locally must have permission to call Vertex AI in the selected project.

For local development, add this role:

```text
Vertex AI User
```

From the Google Cloud Console:

1. Go to **IAM & Admin**.
2. Open **IAM**.
3. Find your Google account, or click **Grant access**.
4. Add the **Vertex AI User** role.
5. Save the change.

If your account also needs to manage APIs, IAM, or billing, your Google Cloud administrator may need to grant additional permissions.

### 4. Install and Initialize Google Cloud CLI

Install the Google Cloud CLI:

```text
https://cloud.google.com/sdk/docs/install
```

Initialize it:

```bash
gcloud init
```

During initialization:

1. Sign in with the Google account that has Vertex AI access.
2. Select the Google Cloud project you created or selected.
3. Set the default region if prompted.

You can manually set the project later:

```bash
gcloud config set project YOUR_PROJECT_ID
```

### 5. Authenticate Locally With Application Default Credentials

Run:

```bash
gcloud auth application-default login
```

This opens a browser sign-in flow and stores local ADC credentials on your machine. Python packages such as `langchain-google-vertexai` can then find those credentials automatically.

Set the ADC quota project:

```bash
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

Verify your active Google Cloud account:

```bash
gcloud auth list
```

### 6. Configure This Project for Vertex AI

In `rag_web/.env`, set:

```env
VERTEX_AI_PROJECT=your_google_cloud_project_id
VERTEX_AI_LOCATION=us-central1
```

No Google API key is required for Vertex AI when ADC is configured correctly.

If you want the app to use the cloud LLM backend by default, keep this setting in `rag_web/rag_web/settings.py`:

```python
DEFAULT_LLM_BACKEND = "cloud"
```

### 7. Google Cloud Policy Rule Notes

Some Google Cloud organizations enforce security policies that can affect setup:

- `iam.disableServiceAccountKeyCreation`: prevents creating downloadable service account JSON keys.
- `iam.disableServiceAccountCreation`: prevents creating new service accounts.
- Newer Google Cloud organizations may have service account key creation disabled by default.

For this local development setup, avoid service account JSON keys unless your organization specifically requires them. Application Default Credentials with `gcloud auth application-default login` is the preferred local approach because it does not require creating or downloading a service account key.

If your organization requires service account impersonation instead of direct user ADC, ask your Google Cloud administrator for:

```text
Service Account Token Creator
```

Then authenticate ADC through impersonation:

```bash
gcloud auth application-default login --impersonate-service-account=SERVICE_ACCOUNT_EMAIL
```

If a policy blocks service account creation or key creation, do not disable the policy casually. Ask an organization policy administrator to approve ADC/user-based development, configure service account impersonation, or create a narrowly scoped project or folder exemption.

## Environment Variables

Create a `.env` file inside the `rag_web` folder:

```bash
cd rag_web
```

Example `rag_web/.env`:

```env
# Django project database
DB_NAME=rag_app_db
DB_USER=rag_user
DB_PASSWORD=strongpassword
DB_HOST=localhost
DB_PORT=5432

# Vector database
VECTOR_DB_NAME=rag_vector_db
VECTOR_DB_USER=vector_user
VECTOR_DB_PASSWORD=vectorpassword
VECTOR_DB_HOST=localhost
VECTOR_DB_PORT=5433

# LLM/API configuration
OPENROUTER_API_KEY=your_openrouter_api_key_here
VERTEX_AI_PROJECT=your_google_cloud_project_id
VERTEX_AI_LOCATION=us-central1

# Optional rate limits
MAX_LLM_TOKENS_PER_MINUTE=1200000
MAX_LLM_REQUESTS_PER_MINUTE=45
```

## Run Database Migrations

From the `rag_web` directory:

```bash
python manage.py migrate
```

## Start the Development Server

From the `rag_web` directory:

```bash
python manage.py runserver
```

Open the app at:

```text
http://127.0.0.1:8000/
```

```sql
-- ============================================================
-- Enum Types
-- ============================================================

CREATE TYPE order_status_enum AS ENUM (
    'delivered',
    'shipped',
    'processing',
    'unavailable',
    'canceled',
    'invoiced'
);


-- ============================================================
-- Sellers Table
-- ============================================================

CREATE TABLE sellers (
    seller_id VARCHAR(50) PRIMARY KEY,
    seller_zip_code_prefix VARCHAR(10),
    seller_city VARCHAR(100),
    seller_state CHAR(2)
);


-- ============================================================
-- Product Category Translation Table
-- ============================================================

CREATE TABLE product_category_translation (
    product_category_name VARCHAR(100) PRIMARY KEY,
    product_category_name_english VARCHAR(100)
);


-- ============================================================
-- Products Table
-- ============================================================

CREATE TABLE products (
    product_id VARCHAR(50) PRIMARY KEY,
    product_category_name VARCHAR(100),
    product_name_lenght INTEGER,
    product_description_lenght INTEGER,
    product_photos_qty INTEGER,
    product_weight_g INTEGER,
    product_length_cm INTEGER,
    product_height_cm INTEGER,
    product_width_cm INTEGER
);


-- ============================================================
-- Customers Table
-- ============================================================

CREATE TABLE customers (
    customer_id VARCHAR(50) PRIMARY KEY,
    customer_unique_id VARCHAR(50),
    customer_zip_code_prefix VARCHAR(10),
    customer_city TEXT,
    customer_state CHAR(2),

    CONSTRAINT chk_customer_state
        CHECK (customer_state ~ '^[A-Z]{2}$')
);


-- ============================================================
-- Orders Table
-- ============================================================

CREATE TABLE orders (
    order_id VARCHAR(50) PRIMARY KEY,
    customer_id VARCHAR(50),
    order_status order_status_enum,
    order_purchase_timestamp TIMESTAMP,
    order_approved_at TIMESTAMP,
    order_delivered_carrier_date TIMESTAMP,
    order_delivered_customer_date TIMESTAMP,
    order_estimated_delivery_date TIMESTAMP
);


-- ============================================================
-- Order Reviews Table
-- ============================================================

CREATE TABLE order_reviews (
    review_id TEXT,
    order_id VARCHAR(50),
    review_score INTEGER CHECK (review_score BETWEEN 1 AND 5),
    review_comment_title TEXT,
    review_comment_message TEXT,
    review_creation_date TIMESTAMP,
    review_answer_timestamp TIMESTAMP
);


-- ============================================================
-- Order Payments Table
-- ============================================================

CREATE TABLE order_payments (
    order_id VARCHAR(50),
    payment_sequential INTEGER,
    payment_type VARCHAR(50),
    payment_installments INTEGER,
    payment_value NUMERIC(10, 2),

    CONSTRAINT chk_payment_value
        CHECK (payment_value >= 0),

    CONSTRAINT chk_payment_installments
        CHECK (payment_installments >= 0)
);


-- ============================================================
-- Order Items Table
-- ============================================================

CREATE TABLE order_items (
    order_id VARCHAR(50),
    order_item_id INTEGER,
    product_id VARCHAR(50),
    seller_id VARCHAR(50),
    shipping_limit_date TIMESTAMP,
    price NUMERIC(10, 2),
    freight_value NUMERIC(10, 2),

    CONSTRAINT chk_order_item_price
        CHECK (price >= 0),

    CONSTRAINT chk_order_item_freight
        CHECK (freight_value >= 0),

    CONSTRAINT order_items_pkey
        PRIMARY KEY (order_id, order_item_id)
);


-- ============================================================
-- Geolocation Table
-- ============================================================

CREATE TABLE geolocation (
    geolocation_zip_code_prefix VARCHAR(10),
    geolocation_lat NUMERIC(10, 8),
    geolocation_lng NUMERIC(11, 8),
    geolocation_city TEXT,
    geolocation_state CHAR(2),

    CONSTRAINT chk_geolocation_lat
        CHECK (geolocation_lat BETWEEN -90 AND 90),

    CONSTRAINT chk_geolocation_lng
        CHECK (geolocation_lng BETWEEN -180 AND 180)
);


-- ============================================================
-- Optional Foreign Key Constraints
-- Add these after importing all CSV files successfully
-- ============================================================

ALTER TABLE orders
ADD CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id)
REFERENCES customers(customer_id);


ALTER TABLE products
ADD CONSTRAINT fk_products_category
FOREIGN KEY (product_category_name)
REFERENCES product_category_translation(product_category_name);


ALTER TABLE order_reviews
ADD CONSTRAINT fk_order_reviews_order
FOREIGN KEY (order_id)
REFERENCES orders(order_id);


ALTER TABLE order_payments
ADD CONSTRAINT fk_order_payments_order
FOREIGN KEY (order_id)
REFERENCES orders(order_id);


ALTER TABLE order_items
ADD CONSTRAINT fk_order_items_order
FOREIGN KEY (order_id)
REFERENCES orders(order_id);


ALTER TABLE order_items
ADD CONSTRAINT fk_order_items_product
FOREIGN KEY (product_id)
REFERENCES products(product_id);


ALTER TABLE order_items
ADD CONSTRAINT fk_order_items_seller
FOREIGN KEY (seller_id)
REFERENCES sellers(seller_id);
```
