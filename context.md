# ARCHITECTURE CONTEXT: UCE-MICROSERVICE

## 1. Technical Stack (Non-Negotiable)
- **Language:** Python 3.11+
- **Framework:** FastAPI (Asynchronous logic)
- **Server:** Uvicorn on Port 8000
- **Validation:** Pydantic V2 schemas
- **Containerization:** Docker (Alpine base image for size optimization)

## 2. API Design Patterns
- **Error Handling:** Global Exception Handlers for 404, 422, and 500.

## 3. Data Integrity
- All endpoints must return a JSON with the keys: `status`, `data`, and `timestamp`.