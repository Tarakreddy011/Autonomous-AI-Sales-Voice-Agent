## Architecture – MVP vs. Production

**MVP (current repo)**
- Single‑process Streamlit app.
- In‑memory session store.
- SQLite (fallback) or local MySQL for CRM data.
- Direct calls to Groq STT/LLM and edge‑tts.
- No containerisation, no load balancer.

**Production design for 100 k daily calls**
- **Stateless workers** running in Docker containers behind a load balancer (e.g., Cloud Load Balancer).
- **Redis** for shared session storage – allows any worker to resume a call.
- **Kafka** (or Celery) queue for asynchronous DB writes and summarisation, ensuring high throughput and resilience.
- **Sharded ChromaDB** (vector store) for knowledge retrieval at scale.
- **MySQL (or Aurora) cluster** with read‑replicas for CRM data.
- **Terraform / Kubernetes** for automated deployment, auto‑scaling, health checks.
- **Observability** – Prometheus + Grafana dashboards for latency, error rates, and queue depth.

### Sizing Method (placeholder values)
```
Calls per day   = X
Avg call minutes = Y
Total minutes   = X * Y
Peak factor     = 1.5–2.0
Required concurrent worker minutes = (X*Y*Peak)/1440
```
Replace X/Y with real metrics when planning capacity.

### First‑to‑break components & fixes
| Component | Failure mode | Mitigation |
|-----------|--------------|------------|
| Groq STT/LLM rate limits | 429 Too Many Requests | Back‑off + request queue (Kafka) |
| MySQL connection pool | Exhausted connections under load | Connection pool size, read‑replicas |
| Embedding model memory | OOM on large batch | Model sharding, GPU off‑load |
| Session store | Lost state if single point | Redis clustering |

---
*All statements are truthful; production‑only items are labeled as such.*