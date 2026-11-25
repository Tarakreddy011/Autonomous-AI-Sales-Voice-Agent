# System Diagrams

## DFD Level 0 (Context Diagram)
```mermaid
flowchart TD
    Customer["Customer"] -->|audio| STT["Groq STT API"]
    STT -->|transcript| Agent["AI Sales Voice Agent"]
    Agent -->|reply text| LLM["Groq LLM API"]
    LLM -->|answer| Agent
    Agent -->|reply audio| TTS["edge‑tts API"]
    TTS -->|audio| Customer
    Agent -->|lead data / booking| MySQL["MySQL (CRM)"]
    MySQL -->|lead & appointment records| Agent
```
> **Explanation:** The context diagram shows the AI Sales Voice Agent as the central process. It receives audio from the Customer, sends it to the STT service, processes the transcript with the LLM, and returns audio via TTS. All lead and booking data flow to/from the MySQL CRM.

## DFD Level 1 (Detailed Processes)
```mermaid
flowchart TD
    subgraph "AI Sales Voice Agent"
        ST[Speech‑to‑Text] --> A[Agent Reasoning]
        A --> TT[Text‑to‑Speech]
        A --> K[Knowledge Retrieval]
        A --> L[Lead & Booking Tools]
    end
    subgraph Stores
        Session[Session Store]
        Chroma[ChromaDB]
        MySQL[MySQL Tables: leads, availability_slots, appointments, call_summaries]
    end
    Customer -->|audio| ST
    ST -->|transcript| A
    K -->|knowledge| A
    L -->|save lead| MySQL
    L -->|check slot| MySQL
    L -->|book appointment| MySQL
    A -->|response text| TT
    TT -->|audio| Customer
    A -->|store session| Session
    A -->|vector queries| Chroma
```
> **Explanation:** This diagram expands the agent into concrete modules that exist in the codebase (`speech_to_text`, `agent_reasoning`, `knowledge_retrieval`, `lead_tool`, `booking_tool`). Data stores include the in‑memory session cache, the vector DB (Chroma), and the MySQL tables.

## UML Use‑Case Diagram
```mermaid
usecaseDiagram
    actor Customer
    actor "Showroom Manager" as Manager
    Customer --> (Speak with Agent)
    (Speak with Agent) --> (Ask product question)
    (Speak with Agent) --> (Share lead details)
    (Speak with Agent) --> (Book showroom visit)
    (Speak with Agent) --> (End call & get summary)
    Manager --> (View leads and summaries)
    Manager --> (View appointments)
```
> **Explanation:** Actors are the Customer and the internal Showroom Manager. The major use‑cases capture the full conversational flow and the managerial view of stored data.

## UML Sequence Diagram – One Full Call
```mermaid
sequenceDiagram
    participant C as Customer
    participant ST as STT Service
    participant A as Agent (Streamlit)
    participant K as Knowledge Tool
    participant L as Lead/Booking Tools
    participant DB as MySQL
    participant T as TTS Service
    C->>ST: Speak
    ST-->>A: Transcript
    A->>K: search_knowledge(query)
    K-->>A: answer
    A->>C: Reply (text)
    C->>A: Provide name, phone, requirement
    A->>L: save_lead(details)
    L->>DB: INSERT lead
    A->>L: check_availability(date)
    L->>DB: SELECT slots
    A->>L: book_appointment(slot)
    L->>DB: UPDATE availability SET is_booked=1 WHERE slot_id AND is_booked=0
    DB-->>L: success/failure
    L->>A: confirmation
    A->>C: Confirmation text
    A->>T: synthesize(reply)
    T-->>C: Audio reply
    C->>A: End Call
    A->>A: summarize_call()
    A->>DB: INSERT call_summary
    A->>C: Summary card
```
> **Explanation:** Shows the exact function calls (`search_knowledge`, `save_lead`, `check_availability`, `book_appointment`, `summarize_call`) that the code executes during a typical call.

## UML Sequence Diagram – Double‑Booking Race
```mermaid
sequenceDiagram
    participant C1 as Caller‑1
    participant C2 as Caller‑2
    participant A as Agent
    participant L as Booking Tool
    participant DB as MySQL
    C1->>A: Request slot X
    C2->>A: Request slot X
    A->>L: book_appointment(slot X)
    L->>DB: UPDATE availability SET is_booked=1 WHERE slot_id=X AND is_booked=0
    alt Success (first request)
        DB-->>L: rows=1
        L-->>A: booked
    else Failure (second request)
        DB-->>L: rows=0
        L-->>A: slot taken, suggest alternatives
    end
```
> **Explanation:** The atomic `UPDATE … WHERE is_booked = 0` guarantees that only the first concurrent request succeeds; the second receives a fallback suggestion.

## UML Class Diagram (Core Classes)
```mermaid
classDiagram
    class VoiceAgent {
        +run()
        +handle_transcript()
        +call_tool()
    }
    class STTService {
        +transcribe(audio) string
    }
    class LLMService {
        +generate(prompt) string
    }
    class TTSService {
        +synthesize(text) audio
    }
    class LeadTool {
        +save_lead(details)
    }
    class BookingTool {
        +check_availability(date)
        +book_appointment(slot)
    }
    class DB {
        +execute(sql, params)
    }
    VoiceAgent --> STTService
    VoiceAgent --> LLMService
    VoiceAgent --> TTSService
    VoiceAgent --> LeadTool
    VoiceAgent --> BookingTool
    LeadTool --> DB
    BookingTool --> DB
```
> **Explanation:** Lists the main Python classes (or modules) that implement the agent’s workflow, showing their responsibilities and database dependency.

## Component Diagram (Deployment View)
```mermaid
graph LR
    subgraph "Client"
        Browser[Web Browser]
    end
    subgraph "Server"
        StreamlitApp[Streamlit UI]
        Agent[VoiceAgent Process]
        DB[MySQL]
        Redis[Redis (session cache)]
        Chroma[ChromaDB]
    end
    Browser -->|HTTP/WebSocket| StreamlitApp
    StreamlitApp --> Agent
    Agent -->|SQL| DB
    Agent -->|Cache| Redis
    Agent -->|Vector| Chroma
    Agent -->|API| STT[Groq STT]
    Agent -->|API| LLM[Groq LLM]
    Agent -->|API| TTS[edge‑tts]
```
> **Explanation:** Shows how the front‑end (Streamlit) talks to the back‑end agent, which in turn uses external APIs and internal data stores. This is the basis for the production design described in `ARCHITECTURE.md`.
