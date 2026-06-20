# Ragnar

Ragnar is a Django-based RAG report generation project. It uses PostgreSQL for the main application database and a PostgreSQL database with `pgvector` support for vector storage.

## Prerequisites

- Git
- Python 3.12 or newer
- Docker
- PostgreSQL client tools are optional, but useful for checking databases manually

## Clone the Project

```bash
git clone https://github.com/exagenio/ragnar.git
cd ragnar
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

Install the Python dependencies from the project requirements file:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If new packages are added during development, update `requirements.txt` so future setups install the same dependencies.

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

## Vertex AI Setup With Google Cloud CLI

This project can use Vertex AI for LLM and embedding models through Google Cloud Application Default Credentials (ADC). ADC lets the Python client libraries authenticate with your local Google Cloud credentials, so you do not need to store a Vertex AI API key in the project.

Use this flow for local development.

### 1. Install the Google Cloud CLI

Install the Google Cloud CLI from the official Google documentation:

```text
https://cloud.google.com/sdk/docs/install
```

After installation, confirm that `gcloud` is available:

```bash
gcloud --version
```

### 2. Initialize gcloud and Select a Project

Run:

```bash
gcloud init
```

During the prompts:

1. Sign in with the Google account you want to use for Vertex AI.
2. Select an existing Google Cloud project, or create one if needed.
3. Make sure billing is enabled for the selected project.

If you already know your project ID, you can set it directly:

```bash
gcloud config set project YOUR_PROJECT_ID
```

Verify the active project:

```bash
gcloud config get-value project
```

### 3. Enable the Vertex AI API

Enable Vertex AI for the selected project:

```bash
gcloud services enable aiplatform.googleapis.com --project YOUR_PROJECT_ID
```

Verify that the API is enabled:

```bash
gcloud services list --enabled --project YOUR_PROJECT_ID --filter="aiplatform.googleapis.com"
```

If this command fails with a permission error, ask a Google Cloud administrator to enable the API or grant you a role that can enable services, such as Service Usage Admin.

### 4. Grant Local Development IAM Roles

The Google account used locally must be allowed to call Vertex AI and use the project for client-library quota and billing.

If you have permission to manage IAM, grant these roles to your user:

```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="user:YOUR_EMAIL_ADDRESS" \
  --role="roles/aiplatform.user"
```

```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="user:YOUR_EMAIL_ADDRESS" \
  --role="roles/serviceusage.serviceUsageConsumer"
```

If you do not have permission to change IAM, ask your Google Cloud administrator to grant:

- `Vertex AI User`
- `Service Usage Consumer`

### 5. Create Application Default Credentials

`gcloud init` authenticates the CLI itself. Python client libraries also need Application Default Credentials.

Run:

```bash
gcloud auth application-default login
```

This opens a browser sign-in flow and stores ADC credentials on your machine.

Set the ADC quota project:

```bash
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

The quota project is used by Google client libraries for billing and quota. The account must have `serviceusage.services.use` permission on the project, which is provided by the `Service Usage Consumer` role.

Verify ADC can produce an access token:

```bash
gcloud auth application-default print-access-token
```

### 6. Configure Ragnar

In `rag_web/.env`, set:

```env
VERTEX_AI_PROJECT=YOUR_PROJECT_ID
VERTEX_AI_LOCATION=us-central1
```

No Google API key is required for Vertex AI when ADC is configured correctly.

If you want the app to use the cloud LLM backend by default, keep this setting in `rag_web/rag_web/settings.py`:

```python
DEFAULT_LLM_BACKEND = "cloud"
```

### 7. Optional: Service Account Impersonation

Some Google Cloud organizations block service account key creation. That is fine for this setup because local ADC does not require downloading service account JSON keys.

If your organization requires service account impersonation, ask your Google Cloud administrator to grant your user:

```text
Service Account Token Creator
```

Then authenticate ADC through impersonation:

```bash
gcloud auth application-default login --impersonate-service-account=SERVICE_ACCOUNT_EMAIL
```

Then set the quota project again:

```bash
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

## Environment Variables

Create a local `.env` file from the example file:

Windows PowerShell:

```powershell
Copy-Item rag_web\.env.example rag_web\.env
```

macOS/Linux:

```bash
cp rag_web/.env.example rag_web/.env
```

Then open `rag_web/.env` and replace the placeholder values with your local database credentials and API configuration.

The example file at `rag_web/.env.example` includes:

- `DB_*` variables for the main Django application database.
- `VECTOR_DB_*` variables for the PostgreSQL/pgvector vector database.
- `OPENROUTER_API_KEY`, `VERTEX_AI_PROJECT`, `VERTEX_AI_LOCATION`, optional `GOOGLE_API_KEY`, and `OLLAMA_BASE_URL` values for LLM providers.
- `MAX_LLM_*`, `TOPIC_PIPELINE_WORKERS`, `VISUAL_PIPELINE_WORKERS`, and SQL worker settings for rate limits and auto-generation concurrency.

## Optional Ollama Local Model Setup

Ragnar can use Ollama as a local model provider if Ollama is installed and running on your machine.

### 1. Install Ollama

Download and install Ollama from the official website:

```text
https://ollama.com/download
```

After installation, verify that Ollama is available:

```bash
ollama --version
```

### 2. Start the Ollama Server

On Windows and macOS, the Ollama desktop app usually starts the local server automatically.

If you need to start it manually, run:

```bash
ollama serve
```

The default local Ollama server URL is:

```env
OLLAMA_BASE_URL=http://localhost:11434
```

Keep this value in `rag_web/.env` unless your Ollama server runs at a different address.

### 3. Pull the Required Chat Models

Ragnar's Ollama provider includes these Llama chat model options:

- `llama3.1:8b`
- `llama3.1:70b`
- `llama3.2:1b`
- `llama3.2:3b`
- `llama3.3:70b`

Pull the models you want to use. For a lightweight local setup, start with:

```bash
ollama pull llama3.1:8b
ollama pull llama3.2:3b
```

If your machine has enough memory, you can also pull the larger models:

```bash
ollama pull llama3.1:70b
ollama pull llama3.3:70b
```

### 4. Pull an Embedding Model

Ragnar also needs an embedding model for metadata vector storage and retrieval when using Ollama.

Recommended:

```bash
ollama pull nomic-embed-text
```

Other supported embedding model options:

```bash
ollama pull mxbai-embed-large
ollama pull all-minilm
```

### 5. Test Ollama Locally

Test a chat model:

```bash
ollama run llama3.1:8b
```

Then type a short prompt, confirm it responds, and exit with `/bye`.

List installed models:

```bash
ollama list
```

### 6. Select Ollama in Ragnar

When creating or editing a project:

1. Set **Model Provider** to **Ollama (Local)**.
2. Select a primary Llama model.
3. Select a secondary Llama model.
4. Select an Ollama embedding model such as `nomic-embed-text`.

If you change the embedding model after metadata has already been generated, regenerate or re-approve metadata so the stored vector embeddings match the selected embedding model.

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

## Example Multi-Table Dataset Setup: Olist Brazilian E-Commerce

You can use the Olist Brazilian E-Commerce dataset to test Ragnar with a real multi-table relational dataset.

### 1. Download the Dataset

Download the dataset from Kaggle:

```text
https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
```

After downloading, extract the ZIP file. The dataset includes CSV files such as:

- `olist_customers_dataset.csv`
- `olist_geolocation_dataset.csv`
- `olist_order_items_dataset.csv`
- `olist_order_payments_dataset.csv`
- `olist_order_reviews_dataset.csv`
- `olist_orders_dataset.csv`
- `olist_products_dataset.csv`
- `olist_sellers_dataset.csv`
- `product_category_name_translation.csv`

### 2. Create a PostgreSQL Database for the Dataset

Run a separate PostgreSQL container for the Olist dataset:

```bash
docker run --name ragnar-olist-postgres \
  -e POSTGRES_DB=olist_ecommerce \
  -e POSTGRES_USER=olist_user \
  -e POSTGRES_PASSWORD=olist_password \
  -p 5434:5432 \
  -v ragnar_olist_data:/var/lib/postgresql/data \
  -d postgres:16
```

Windows PowerShell single-line version:

```powershell
docker run --name ragnar-olist-postgres -e POSTGRES_DB=olist_ecommerce -e POSTGRES_USER=olist_user -e POSTGRES_PASSWORD=olist_password -p 5434:5432 -v ragnar_olist_data:/var/lib/postgresql/data -d postgres:16
```

Connection details:

- Host: `localhost`
- Port: `5434`
- Database: `olist_ecommerce`
- User: `olist_user`
- Password: `olist_password`

### 3. Install pgAdmin or Another PostgreSQL Client

You can import the CSV files using pgAdmin. If pgAdmin is not installed, download the latest version from the official pgAdmin download page:

```text
https://www.pgadmin.org/download/
```

You can also use another PostgreSQL client such as DBeaver, DataGrip, or the `psql` command-line tool.

### 4. Create the Tables

Open pgAdmin, connect to the `olist_ecommerce` database, open the Query Tool, and run the table creation script below.

Recommended import flow:

1. Run the enum and `CREATE TABLE` statements first.
2. Import the CSV files into their matching tables.
3. Run the `ALTER TABLE ... ADD CONSTRAINT` foreign key statements after all CSV files are imported.

CSV-to-table mapping:

- `olist_customers_dataset.csv` -> `customers`
- `olist_geolocation_dataset.csv` -> `geolocation`
- `olist_order_items_dataset.csv` -> `order_items`
- `olist_order_payments_dataset.csv` -> `order_payments`
- `olist_order_reviews_dataset.csv` -> `order_reviews`
- `olist_orders_dataset.csv` -> `orders`
- `olist_products_dataset.csv` -> `products`
- `olist_sellers_dataset.csv` -> `sellers`
- `product_category_name_translation.csv` -> `product_category_translation`

In pgAdmin, right-click a table, select **Import/Export Data**, choose the matching CSV file, enable **Header**, set the format to **CSV**, and import the data.

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

## Example Single-Table Dataset Setup: Retail Store Sales Transactions

You can use the Retail Store Sales Transactions dataset to test Ragnar with a single-table dataset.

### 1. Download the Dataset

Download the dataset from Kaggle:

```text
https://www.kaggle.com/datasets/marian447/retail-store-sales-transactions
```

After downloading, extract the ZIP file and locate the retail transactions CSV file.

### 2. Create a PostgreSQL Database for the Dataset

Run a separate PostgreSQL container for the retail transactions dataset:

```bash
docker run --name ragnar-retail-postgres \
  -e POSTGRES_DB=retail_sales \
  -e POSTGRES_USER=retail_user \
  -e POSTGRES_PASSWORD=retail_password \
  -p 5435:5432 \
  -v ragnar_retail_data:/var/lib/postgresql/data \
  -d postgres:16
```

Windows PowerShell single-line version:

```powershell
docker run --name ragnar-retail-postgres -e POSTGRES_DB=retail_sales -e POSTGRES_USER=retail_user -e POSTGRES_PASSWORD=retail_password -p 5435:5432 -v ragnar_retail_data:/var/lib/postgresql/data -d postgres:16
```

Connection details:

- Host: `localhost`
- Port: `5435`
- Database: `retail_sales`
- User: `retail_user`
- Password: `retail_password`

### 3. Create the Single Table

Open pgAdmin, connect to the `retail_sales` database, open the Query Tool, and run this table creation script:

```sql
CREATE TABLE retail_transactions (
    "Id" BIGINT PRIMARY KEY,
    "Date" DATE,
    "Customer_ID" INTEGER,
    "Transaction_ID" INTEGER,
    "SKU_Category" VARCHAR(255),
    "SKU" VARCHAR(255),
    "Quantity" NUMERIC,
    "Sales_Amount" NUMERIC
);
```

### 4. Import the CSV Data

In pgAdmin, right-click `retail_transactions`, select **Import/Export Data**, choose the downloaded CSV file, enable **Header**, set the format to **CSV**, and import the data.

After importing, use these connection details in Ragnar when creating a project for this dataset. Since this is a single-table dataset, select only the `retail_transactions` table during metadata generation.
