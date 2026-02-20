# Twilio AI Voice Assistant

A modular FastAPI application that provides an AI-powered voice assistant using Twilio, Sarvam AI, and Groq.

## Project Structure

```
twilio/
├── main.py                          # Application entry point and route definitions
├── config.py                        # Configuration and environment variables
├── services/                        # Business logic modules
│   ├── __init__.py
│   ├── twilio_service.py           # Twilio call operations
│   ├── sarvam_service.py           # Text-to-Speech and Speech-to-Text
│   └── llm_service.py              # AI response generation (Groq)
└── routes/                          # API route handlers
    ├── __init__.py
    └── call_routes.py              # Call-related endpoints
```

## Modules

### `config.py`
Central configuration for all API keys, URLs, and environment variables.

### `services/`
Contains all external service integrations:
- **twilio_service.py**: Handles outbound call initiation
- **sarvam_service.py**: Text-to-Speech and Speech-to-Text using Sarvam AI
- **llm_service.py**: AI conversation logic using Groq's LLM

### `routes/`
API endpoint handlers:
- **call_routes.py**: Contains logic for `/call`, `/voice`, and `/process` endpoints

### `main.py`
FastAPI application initialization and route registration. Clean entry point with minimal code.

## Setup

1. Create a `.env` file with the following variables:
```env
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
GROQ_API_KEY=your_groq_key
SARVAM_API_KEY=your_sarvam_key
```

2. Update the `BASE_URL` in [config.py](config.py) with your ngrok or public URL.

3. Install dependencies:
```bash
pip install fastapi twilio groq httpx python-dotenv uvicorn
```

4. Run the application:
```bash
uvicorn main:app --reload
```

## API Endpoints

- **POST /call**: Initiates an outbound call
- **POST /voice**: Webhook for incoming calls
- **POST /process**: Processes recorded audio and generates AI responses

## Benefits of Modular Structure

- **Separation of Concerns**: Each module has a single, well-defined responsibility
- **Easier Testing**: Services can be tested independently
- **Better Maintainability**: Changes to one service don't affect others
- **Scalability**: Easy to add new services or routes
- **Code Reusability**: Services can be imported and used across different routes
