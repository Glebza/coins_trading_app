graph TD
    subgraph "Frontend - React SPA"
        UI[User Interface]
        AuthUI[Authentication UI]
        MapUI[Game Map UI]
        CharUI[Character Sheet UI]
        QuestUI[Quest Management UI]
        AnalyticsUI[Analytics Dashboard]
        RewardsUI[Rewards & Achievements UI]
        JournalUI[Journal & Reflection UI]
        
        Redux[Redux Store]
        SocketClient[Socket.io Client]
        
        UI --> AuthUI
        UI --> MapUI
        UI --> CharUI
        UI --> QuestUI
        UI --> AnalyticsUI
        UI --> RewardsUI
        UI --> JournalUI
        
        AuthUI <--> Redux
        MapUI <--> Redux
        CharUI <--> Redux
        QuestUI <--> Redux
        AnalyticsUI <--> Redux
        RewardsUI <--> Redux
        JournalUI <--> Redux
        
        Redux <--> APIClient[API Client]
        Redux <--> SocketClient
    end
    
    subgraph "Backend - Python FastAPI"
        APIGateway[API Gateway]
        
        AuthService[Authentication Service]
        UserService[User Service]
        GoalsService[Goals Service]
        SkillsService[Skills Service]
        IncomeService[Income & Career Service]
        AchievementsService[Achievements Service]
        AnalyticsService[Analytics Service]
        WellbeingService[Wellbeing Service]
        
        WSServer[WebSocket Server]
        
        APIGateway --> AuthService
        APIGateway --> UserService
        APIGateway --> GoalsService
        APIGateway --> SkillsService
        APIGateway --> IncomeService
        APIGateway --> AchievementsService
        APIGateway --> AnalyticsService
        APIGateway --> WellbeingService
        
        AchievementsService --> WSServer
        GoalsService --> AchievementsService
        SkillsService --> AchievementsService
        IncomeService --> AchievementsService
        WellbeingService --> AnalyticsService
    end
    
    subgraph "Data Layer"
        PostgreSQL[(PostgreSQL)]
        Redis[(Redis Cache)]
        
        UserService <--> PostgreSQL
        GoalsService <--> PostgreSQL
        SkillsService <--> PostgreSQL
        IncomeService <--> PostgreSQL
        AchievementsService <--> PostgreSQL
        WellbeingService <--> PostgreSQL
        
        AuthService <--> Redis
        AnalyticsService <--> Redis
    end
    
    APIClient <--> APIGateway
    SocketClient <--> WSServer
    
    classDef frontend fill:#f9f,stroke:#333,stroke-width:2px;
    classDef backend fill:#bbf,stroke:#333,stroke-width:2px;
    classDef database fill:#bfb,stroke:#333,stroke-width:2px;
    
    class UI,AuthUI,MapUI,CharUI,QuestUI,AnalyticsUI,RewardsUI,JournalUI,Redux,SocketClient,APIClient frontend;
    class APIGateway,AuthService,UserService,GoalsService,SkillsService,IncomeService,AchievementsService,AnalyticsService,WellbeingService,WSServer backend;
    class PostgreSQL,Redis database;
