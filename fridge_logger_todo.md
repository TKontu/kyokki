# Refrigerator Content Logger - Homelab TODO

## Phase 1: Infrastructure & Core Setup (Weeks 1-4)

### Week 1: Homelab Environment Setup

- [x] **Infrastructure Preparation**

  - [x] Set up Docker and Docker Compose on homelab server
  - [x] Create project directory structure on homelab
  - [x] Configure network settings and port allocations
  - [ ] Set up SSL certificates (self-signed or local CA)
  - [ ] Configure reverse proxy (Nginx/Traefik) for iPad access
  - [x] Test basic network connectivity from iPad

- [x] **Ollama Installation & Model Setup**
  - [x] Install Ollama on homelab server
  - [x] Download and test Qwen2-VL-7B model
  - [x] Configure Ollama service settings
  - [x] Test model inference with sample images

### Week 2: Database & Backend Foundation

- [x] **Database Setup**

  - [x] Deploy PostgreSQL container with Docker Compose
  - [x] Create database schema and migrations with SQLAlchemy
  - [x] Set up connection pooling and async support
  - [ ] Configure automated backup scripts
  - [ ] Create database seeding scripts for products
  - [x] Set up Redis for background task queue

- [x] **Python Backend Core**
  - [x] Initialize FastAPI project structure
  - [x] Set up async SQLAlchemy models and database connection
  - [x] Configure environment variables and secrets management
  - [x] Implement basic health check endpoints
  - [ ] Set up structured logging
  - [x] Create Docker container for backend service

### Week 3: AI Integration & Image Processing

- [x] **Ollama Integration**

  - [x] Create async Ollama client wrapper
  - [x] Implement product identification pipeline
  - [x] Build expiration date extraction logic
  - [x] Add confidence scoring and validation
  - [x] Create structured output parsing
  - [x] Implement error handling and retries

- [x] **Image Processing Pipeline**
  - [ ] Set up image preprocessing (resize, enhance, format conversion)
  - [x] Create async file upload handling
  - [x] Implement image storage organization
  - [ ] Add thumbnail generation
  - [x] Build background processing queue with Celery
  - [ ] Create batch processing capabilities

### Week 4: Core API Development

- [x] **REST API Endpoints**

  - [x] POST /api/items/analyze - Upload and analyze images
  - [x] GET /api/items - Retrieve items sorted by expiry
  - [x] PUT /api/items/:id - Update item details
  - [x] DELETE /api/items/:id - Soft delete with undo capability
  - [x] POST /api/items/:id/restore - Restore deleted items
  - [x] GET /api/health - System health and status

- [x] **WebSocket Integration**
  - [x] Set up WebSocket connections for real-time updates
  - [x] Implement processing status notifications
  - [x] Add real-time item list updates
  - [x] Create connection management for iPad
  - [x] Handle reconnection logic

## Phase 2: iPad Interface Development (Weeks 5-8)

### Week 5: Frontend Foundation

- [x] **React/Next.js Setup**

  - [x] Initialize Next.js project with PWA support
  - [x] Configure Tailwind CSS for iPad viewport
  - [x] Set up state management (React Query + Zustand)
  - [x] Configure API client with homelab endpoint
  - [ ] Implement authentication (if needed)
  - [x] Create responsive layout for iPad

  - [] **Technical Debt & Refactoring**

  - [ ] **Decouple Celery Worker from API with Redis Pub/Sub**
    - [ ] **Goal:** Eliminate `asyncio` event loop errors and create a more robust architecture.
    - [ ] **Celery Task (`tasks.py`):** Modify the `analyze_image_task` to publish the new item's JSON data to a Redis "item_updates" channel instead of calling the WebSocket manager directly.
    - [ ] **FastAPI App (`main.py`):** Implement a `lifespan` event handler to start a background task on application startup.
    - [ ] **Background Task:** The new task will subscribe to the "item_updates" Redis channel.
    - [ ] **WebSocket Manager (`websockets.py`):** When the background task receives a message from Redis, it will use the existing `manager.broadcast()` method to send the data to all connected clients from the correct event loop.

- [ ] **PWA Configuration**
  - [ ] Create app manifest for home screen installation
  - [ ] Implement service worker for offline support
  - [ ] Set up background sync capabilities
  - [ ] Configure cache strategies for images and data
  - [ ] Add "Add to Home Screen" prompts
  - [ ] Test offline functionality

### Week 6: Camera & Image Upload

- [ ] **Camera Integration**

  - [ ] Implement WebRTC camera access for iPad
  - [ ] Create touch-optimized camera interface
  - [ ] Add image preview and retake functionality
  - [ ] Implement image compression before upload
  - [ ] Support multiple image selection
  - [ ] Add camera permission handling

- [x] **Upload & Processing UI**
  - [x] Create drag-and-drop image upload
  - [x] Implement upload progress indicators
  - [x] Add real-time processing status updates
  - [ ] Create image preview gallery
  - [ ] Build processing queue visualization
  - [x] Add error handling for failed uploads

### Week 7: Item Management Interface

- [x] **Item List & Display**

  - [x] Create item list sorted by expiry date
  - [x] Implement color-coded expiry warnings
  - [x] Add touch-optimized item cards
  - [x] Create status indicators (unopened/opened)
  - [ ] Build search and filter functionality
  - [ ] Add infinite scrolling for large lists

- [ ] **Item Interaction**
  - [ ] Implement swipe gestures for delete/edit
  - [ ] Create edit modal with touch keyboard
  - [ ] Add status toggle buttons (unopened/opened)
  - [ ] Build undo system with toast notifications
  - [ ] Create bulk selection and operations
  - [ ] Add manual item entry form

### Week 8: iPad Optimization & Testing

- [ ] **iPad-Specific Optimizations**

  - [ ] Optimize for landscape and portrait modes
  - [ ] Test with iPad sleep/wake cycles
  - [ ] Implement auto-refresh for always-on display
  - [ ] Optimize battery usage and performance
  - [ ] Test touch responsiveness and gestures
  - [ ] Handle Safari-specific quirks

- [ ] **Integration Testing**
  - [ ] End-to-end testing with real food images
  - [ ] Test offline-to-online sync scenarios
  - [ ] Validate WebSocket reconnection handling
  - [ ] Performance testing with large item lists
  - [ ] Network failure recovery testing
  - [ ] Multi-session handling tests

## Phase 3: Enhancement & Production (Weeks 9-12)

### Week 9: Advanced Features

- [ ] **Smart Product Database**

  - [ ] Build comprehensive product database
  - [ ] Implement smart product matching
  - [ ] Add category-based shelf life rules
  - [ ] Create brand recognition improvements
  - [ ] Build product learning from user corrections
  - [ ] Add barcode support preparation

- [ ] **Status Management System**
  - [ ] Implement "opened" status with adjusted expiry
  - [ ] Add custom shelf-life overrides
  - [ ] Create consumption tracking
  - [ ] Build usage pattern recognition
  - [ ] Add quantity management
  - [ ] Create waste tracking analytics

### Week 10: Monitoring & Administration

- [ ] **System Monitoring**

  - [ ] Set up Prometheus metrics collection
  - [ ] Create Grafana dashboards for monitoring
  - [ ] Implement log aggregation and analysis
  - [ ] Add performance monitoring
  - [ ] Create automated alerting system
  - [ ] Build system health dashboard

- [ ] **Administration Interface**
  - [ ] Create admin panel for product database management
  - [ ] Build user activity monitoring
  - [ ] Add system configuration interface
  - [ ] Implement backup and restore tools
  - [ ] Create model management interface
  - [ ] Add maintenance mode capabilities

### Week 11: Performance & Reliability

- [ ] **Performance Optimization**

  - [ ] Implement intelligent caching strategies
  - [ ] Optimize database queries and indexing
  - [ ] Reduce image processing latency
  - [ ] Minimize iPad battery usage
  - [ ] Optimize network requests and payloads

- [ ] **Reliability Improvements**
  - [ ] Implement circuit breakers for external dependencies
  - [ ] Add comprehensive error recovery mechanisms
  - [ ] Create automated failover procedures
  - [ ] Build data consistency checks
  - [ ] Implement graceful degradation modes
  - [ ] Add automated system recovery

### Week 12: Documentation & Deployment

- [ ] **Production Deployment**

  - [ ] Create production Docker Compose configuration
  - [ ] Set up automated deployment pipeline
  - [ ] Configure production monitoring and logging
  - [ ] Implement security hardening measures
  - [ ] Set up automated backups and recovery
  - [ ] Create disaster recovery procedures

- [ ] **Documentation**
  - [ ] Write homelab setup and installation guide
  - [ ] Create iPad app user manual
  - [ ] Document API endpoints and WebSocket events
  - [ ] Build troubleshooting and maintenance guide
  - [ ] Create backup and recovery procedures

## Phase 4: Advanced Features (Weeks 13-16)

### Week 13: Recipe Integration

- [ ] **Local Recipe Database**
  - [ ] Create local recipe database schema
  - [ ] Import recipe data (JSON/CSV format)
  - [ ] Build recipe matching algorithm based on available items
  - [ ] Create "use expiring items first" recipe suggestions
  - [ ] Add recipe difficulty and time filtering
  - [ ] Implement recipe favorites and ratings

### Week 14: Shopping & Planning

- [ ] **Shopping List Management**
  - [ ] Create automated shopping list generation
  - [ ] Build "buy more" suggestions based on usage patterns
  - [ ] Add quantity tracking and consumption rates
  - [ ] Create shopping list sharing capabilities
  - [ ] Implement store-specific organization
  - [ ] Add price tracking and budgeting

### Week 15: Analytics & Insights

- [ ] **Usage Analytics**
  - [ ] Build food waste tracking and reporting
  - [ ] Create consumption pattern analysis
  - [ ] Add cost tracking and budget insights
  - [ ] Implement seasonal trend analysis
  - [ ] Create sustainability metrics
  - [ ] Build custom dashboard for insights

### Week 16: Integration & Expansion

- [ ] **Home Automation Integration**
  - [ ] Create Home Assistant integration
  - [ ] Add MQTT support for IoT devices
  - [ ] Implement voice assistant integration
  - [ ] Build notification systems (push, email)
  - [ ] Add calendar integration for meal planning
  - [ ] Create family sharing capabilities

## Maintenance & Operations

### Regular Maintenance Tasks

- [ ] **Weekly**

  - [ ] Monitor system resource usage
  - [ ] Check backup integrity
  - [ ] Review error logs and metrics
  - [ ] Update security patches

- [ ] **Monthly**

  - [ ] Update dependencies and Docker images
  - [ ] Review and optimize database performance
  - [ ] Analyze usage patterns and optimize
  - [ ] Test disaster recovery procedures

- [ ] **Quarterly**
  - [ ] Update Ollama models
  - [ ] Security audit and penetration testing
  - [ ] Performance benchmarking
  - [ ] Capacity planning review

### Success Metrics

- [ ] **Technical Metrics**

  - [ ] AI accuracy rate: >80% for product identification
  - [ ] Response time: <2s for image processing
  - [ ] Uptime: >99.5% availability
  - [ ] iPad battery life: Full day usage support

- [ ] **User Experience Metrics**
  - [ ] Time to add item: <30 seconds
  - [ ] Touch interface responsiveness: <100ms
  - [ ] Offline functionality: 24h+ capability
  - [ ] Error rate: <2% for image processing

### Troubleshooting Checklist

- [ ] Ollama model not responding
- [ ] iPad connection issues
- [ ] Database performance problems
- [ ] Image processing failures
- [ ] WebSocket disconnections
- [ ] Storage space management
