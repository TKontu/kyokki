# Refrigerator Content Logger - Homelab Architecture Design

## System Overview

A self-hosted refrigerator content management system running on homelab infrastructure, using local AI models via Ollama for privacy and reliability, with an iPad as the primary interface.

## Architecture Components

### 1. Frontend Layer (iPad Interface)

**Technology Stack:**

- **Framework**: React/Next.js with PWA capabilities
- **Styling**: Tailwind CSS optimized for iPad viewport
- **State Management**: React Query + Zustand
- **Camera**: WebRTC APIs for photo capture
- **Deployment**: Static files served by Python backend

**iPad-Specific Optimizations:**

- Touch-optimized interface with large buttons
- Landscape orientation support
- Always-on display considerations
- Low-power mode compatibility
- Offline-first architecture with sync

### 2. Backend API Layer (Python)

**Technology Stack:**

- **Framework**: FastAPI (async support, automatic docs)
- **File Handling**: aiofiles for async file operations
- **Image Processing**: Pillow + OpenCV for preprocessing
- **Database ORM**: SQLAlchemy with async support
- **Background Tasks**: Celery with Redis
- **Static Files**: Serve React build directly

**Key Features:**

- Async request handling for better performance
- Background image processing queue
- WebSocket support for real-time updates
- Automatic API documentation
- Health check endpoints for monitoring

### 3. AI/ML Integration Layer (Local Ollama)

**Model Setup:**

- **Primary Model**: Qwen2-VL-7B via Ollama
- **Backup Model**: LLaVA or MiniCPM-V for redundancy
- **Preprocessing**: Local image optimization before inference
- **Post-processing**: Structured output parsing

**Ollama Integration:**

```python
# Example integration
import ollama

async def analyze_product_image(image_path: str):
    response = ollama.chat(
        model='qwen2-vl:7b',
        messages=[{
            'role': 'user',
            'content': 'Analyze this food product image...',
            'images': [image_path]
        }]
    )
    return parse_product_info(response['message']['content'])
```

**Performance Optimizations:**

- Model preloading on server start
- Image batch processing for multiple items
- Caching frequent product identifications
- GPU acceleration if available

### 4. Database Layer (Local PostgreSQL)

**Database**: PostgreSQL running in Docker container

**Schema Design:**

```sql
-- Core tables optimized for homelab
items (
  id UUID PRIMARY KEY,
  product_name VARCHAR(255),
  brand VARCHAR(255),
  expiry_date DATE,
  status item_status DEFAULT 'unopened',
  confidence_score FLOAT,
  image_path VARCHAR(500),
  date_added TIMESTAMP DEFAULT NOW(),
  date_modified TIMESTAMP DEFAULT NOW(),
  is_deleted BOOLEAN DEFAULT FALSE,
  deleted_at TIMESTAMP NULL,
  manual_override BOOLEAN DEFAULT FALSE
);

products_database (
  id UUID PRIMARY KEY,
  product_name VARCHAR(255),
  category product_category,
  default_shelf_life INTERVAL,
  opened_shelf_life INTERVAL,
  storage_type storage_type,
  barcode VARCHAR(50),
  common_brands TEXT[]
);

processing_queue (
  id UUID PRIMARY KEY,
  image_path VARCHAR(500),
  status queue_status DEFAULT 'pending',
  created_at TIMESTAMP DEFAULT NOW(),
  processed_at TIMESTAMP NULL,
  error_message TEXT NULL
);
```

### 5. Storage Layer (Local NAS/Storage)

**Image Storage Structure:**

```
/data/fridge-logger/
├── images/
│   ├── raw/          # Original uploaded images
│   ├── processed/    # Preprocessed for AI
│   └── thumbnails/   # UI thumbnails
├── models/           # Ollama model cache
├── backups/          # Database backups
└── logs/            # Application logs
```

## Homelab Deployment Architecture

### Docker Compose Stack

```yaml
version: "3.8"
services:
  fridge-logger-api:
    build: ./backend
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./config:/app/config
    depends_on:
      - postgres
      - redis
      - ollama

  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: fridge_logger
      POSTGRES_USER: fridge_user
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
```

### Network Configuration

- **Internal Network**: All services communicate via Docker network
- **External Access**: Reverse proxy (Nginx/Traefik) for iPad access
- **SSL/TLS**: Self-signed certificates or local CA
- **Port Mapping**:
  - 80/443: Web interface (iPad)
  - 8000: API (internal)
  - 5432: PostgreSQL (internal)
  - 192.168.0.247:11434: Ollama (external)
  - 192.168.0.136:11434: Ollama (external, redundancy)

### iPad-Specific Configuration

**PWA Setup:**

- Service worker for offline functionality
- App manifest for home screen installation
- Background sync for when iPad wakes up
- Optimized for Safari/WebKit

**Always-On Considerations:**

- Auto-refresh mechanism for data updates
- Battery optimization
- Screen timeout handling
- Network reconnection logic

## Data Flow (Homelab Optimized)

### Adding New Item (iPad → Homelab)

1. iPad captures photo via camera API
2. Image uploaded to Python backend
3. Backend queues image for processing
4. Ollama processes image locally (no external API calls)
5. Results stored in local PostgreSQL
6. iPad receives real-time update via WebSocket
7. User can review and edit via touch interface

### Offline Handling

1. iPad caches recent data locally
2. Images stored temporarily when offline
3. Background sync when connection restored
4. Conflict resolution for concurrent edits

## Performance Considerations

### Ollama Optimization

- **Model Loading**: Keep Qwen2-VL-7B loaded in memory
- **Batch Processing**: Process multiple images together
- **Hardware**: Recommend 16GB+ RAM, GPU optional but beneficial
- **Caching**: Cache common product identifications

### iPad Interface Optimization

- **Image Compression**: Reduce upload size while maintaining quality
- **Lazy Loading**: Load item images on demand
- **Touch Responsiveness**: Optimize for 60fps interactions
- **Battery Efficiency**: Minimize background processing

### Database Optimization

- **Indexing**: Expiry date, product name, status columns
- **Archiving**: Move old deleted items to archive table
- **Backup Strategy**: Automated nightly backups
- **Connection Pooling**: Handle concurrent iPad requests

## Monitoring & Maintenance

### Health Monitoring

- **Service Health**: API, database, Ollama status endpoints
- **Performance Metrics**: Response times, processing queue length
- **Resource Usage**: CPU, memory, disk space monitoring
- **Error Tracking**: Structured logging with alerts

### Backup Strategy

- **Database**: Automated PostgreSQL dumps
- **Images**: Incremental backups to external storage
- **Configuration**: Version controlled docker-compose and configs
- **Model Cache**: Backup Ollama models and fine-tuning data

### Updates & Maintenance

- **Dependency Updates**: Automated security patches
- **Model Updates**: Periodic Ollama model updates
- **Database Maintenance**: Regular VACUUM and analysis
- **Log Rotation**: Prevent disk space issues

## Security Considerations (Homelab)

### Network Security

- **Internal Network**: Docker networks for service isolation
- **Firewall**: Only expose necessary ports
- **Access Control**: IP whitelisting for iPad
- **SSL/TLS**: Encrypted communication even internally

### Data Privacy

- **Local Processing**: All AI processing stays on homelab
- **No External APIs**: Complete data sovereignty
- **Backup Encryption**: Encrypted backup storage
- **Access Logs**: Monitor all data access

## Scalability (Homelab Context)

### Vertical Scaling

- **RAM**: More memory for better Ollama performance
- **Storage**: NAS expansion for image storage
- **GPU**: Add GPU for faster AI processing
- **CPU**: Multi-core for concurrent processing

### Feature Expansion

- **Multi-User**: Family member profiles
- **Multiple Devices**: Additional iPads or phones
- **Integration**: Home Assistant integration
- **Analytics**: Local analytics dashboard
