"""Skill dictionary: matching technology and competency terms in resumés and JDs.

The dictionary is data, not code. A bundled seed provides a baseline that works
without a database, and approved rows in ``skill_aliases`` extend or override it
at runtime so new terminology does not require a code change and a redeploy.

Design notes:
- One compiled alternation is used for the whole dictionary instead of one
  ``re.search`` per skill, so matching cost does not grow with dictionary size.
- ASCII aliases are matched with word boundaries so ``Java`` never matches
  inside ``JavaScript``.
- A short deny-list of ambiguous aliases (``Go``) additionally rejects a
  following lowercase word, so English prose such as "Go to market" is not
  reported as the Go language.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

CATEGORY_LANGUAGE = "编程语言"
CATEGORY_FRONTEND = "前端"
CATEGORY_BACKEND = "后端框架"
CATEGORY_DATABASE = "数据库"
CATEGORY_MIDDLEWARE = "中间件"
CATEGORY_CLOUD = "云原生与运维"
CATEGORY_BIGDATA = "大数据"
CATEGORY_AI = "人工智能"
CATEGORY_TESTING = "测试与质量"
CATEGORY_TOOLING = "工具与协作"
CATEGORY_SYSTEM = "操作系统与网络"
CATEGORY_SOFT = "软技能"

# Aliases that are also ordinary English words. They only match when not
# followed by another lowercase word, which keeps "Go to market" out while
# still matching "Go、Python" and "Go / Kubernetes" in a skill list.
AMBIGUOUS_ALIASES = frozenset({"go"})

_RAW_SEED: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # 编程语言
    ("Python", CATEGORY_LANGUAGE, ("python3", "python2")),
    ("Java", CATEGORY_LANGUAGE, ("java8", "java11", "java17")),
    ("Go", CATEGORY_LANGUAGE, ("golang", "go语言")),
    ("C++", CATEGORY_LANGUAGE, ("cpp", "c plus plus")),
    ("C#", CATEGORY_LANGUAGE, ("csharp", ".net")),
    ("C", CATEGORY_LANGUAGE, ("c语言",)),
    ("Rust", CATEGORY_LANGUAGE, ()),
    ("Kotlin", CATEGORY_LANGUAGE, ()),
    ("Scala", CATEGORY_LANGUAGE, ()),
    ("PHP", CATEGORY_LANGUAGE, ()),
    ("Ruby", CATEGORY_LANGUAGE, ()),
    ("Swift", CATEGORY_LANGUAGE, ()),
    ("Objective-C", CATEGORY_LANGUAGE, ("objective c", "oc")),
    ("Dart", CATEGORY_LANGUAGE, ()),
    ("Lua", CATEGORY_LANGUAGE, ()),
    ("Perl", CATEGORY_LANGUAGE, ()),
    ("R", CATEGORY_LANGUAGE, ("r语言",)),
    ("MATLAB", CATEGORY_LANGUAGE, ()),
    ("Shell", CATEGORY_LANGUAGE, ("bash", "shell脚本")),
    ("SQL", CATEGORY_LANGUAGE, ()),
    ("Verilog", CATEGORY_LANGUAGE, ()),
    ("VHDL", CATEGORY_LANGUAGE, ()),
    ("汇编", CATEGORY_LANGUAGE, ("assembly",)),
    # 前端
    ("JavaScript", CATEGORY_FRONTEND, ("js", "es6", "ecmascript")),
    ("TypeScript", CATEGORY_FRONTEND, ("ts",)),
    ("HTML", CATEGORY_FRONTEND, ("html5",)),
    ("CSS", CATEGORY_FRONTEND, ("css3",)),
    ("React", CATEGORY_FRONTEND, ("react.js", "reactjs")),
    ("Vue", CATEGORY_FRONTEND, ("vue.js", "vuejs", "vue2", "vue3")),
    ("Angular", CATEGORY_FRONTEND, ()),
    ("Svelte", CATEGORY_FRONTEND, ()),
    ("Next.js", CATEGORY_FRONTEND, ("nextjs", "next js")),
    ("Nuxt.js", CATEGORY_FRONTEND, ("nuxtjs",)),
    ("Webpack", CATEGORY_FRONTEND, ()),
    ("Vite", CATEGORY_FRONTEND, ()),
    ("Rollup", CATEGORY_FRONTEND, ()),
    ("Babel", CATEGORY_FRONTEND, ()),
    ("Tailwind CSS", CATEGORY_FRONTEND, ("tailwind", "tailwindcss")),
    ("Sass", CATEGORY_FRONTEND, ("scss",)),
    ("Less", CATEGORY_FRONTEND, ()),
    ("jQuery", CATEGORY_FRONTEND, ()),
    ("小程序", CATEGORY_FRONTEND, ("微信小程序",)),
    ("Flutter", CATEGORY_FRONTEND, ()),
    ("React Native", CATEGORY_FRONTEND, ("reactnative",)),
    ("Electron", CATEGORY_FRONTEND, ()),
    ("WebGL", CATEGORY_FRONTEND, ()),
    ("Three.js", CATEGORY_FRONTEND, ("threejs",)),
    ("ECharts", CATEGORY_FRONTEND, ()),
    # 后端框架
    ("Node.js", CATEGORY_BACKEND, ("nodejs", "node js")),
    ("FastAPI", CATEGORY_BACKEND, ()),
    ("Django", CATEGORY_BACKEND, ("django rest framework", "drf")),
    ("Flask", CATEGORY_BACKEND, ()),
    ("Tornado", CATEGORY_BACKEND, ()),
    ("Spring", CATEGORY_BACKEND, ()),
    ("Spring Boot", CATEGORY_BACKEND, ("springboot",)),
    ("Spring Cloud", CATEGORY_BACKEND, ("springcloud",)),
    ("MyBatis", CATEGORY_BACKEND, ()),
    ("Netty", CATEGORY_BACKEND, ()),
    ("Gin", CATEGORY_BACKEND, ("gin框架",)),
    ("Echo", CATEGORY_BACKEND, ()),
    ("Express", CATEGORY_BACKEND, ("express.js", "expressjs")),
    ("NestJS", CATEGORY_BACKEND, ("nest.js",)),
    ("Koa", CATEGORY_BACKEND, ()),
    ("gRPC", CATEGORY_BACKEND, ("grpc",)),
    ("RESTful API", CATEGORY_BACKEND, ("rest api", "restful", "rest接口")),
    ("GraphQL", CATEGORY_BACKEND, ()),
    ("WebSocket", CATEGORY_BACKEND, ("websocket",)),
    ("Microservices", CATEGORY_BACKEND, ("微服务", "microservice")),
    ("OAuth", CATEGORY_BACKEND, ("oauth2",)),
    ("JWT", CATEGORY_BACKEND, ()),
    ("SSO", CATEGORY_BACKEND, ("单点登录",)),
    ("高并发", CATEGORY_BACKEND, ("高并发系统",)),
    ("分布式", CATEGORY_BACKEND, ("分布式系统", "distributed")),
    ("消息队列", CATEGORY_BACKEND, ("mq", "message queue")),
    ("缓存", CATEGORY_BACKEND, ("cache", "缓存中间件")),
    ("限流", CATEGORY_BACKEND, ("熔断", "降级")),
    # 数据库
    ("MySQL", CATEGORY_DATABASE, ()),
    ("PostgreSQL", CATEGORY_DATABASE, ("postgres", "pgsql")),
    ("Oracle", CATEGORY_DATABASE, ()),
    ("SQL Server", CATEGORY_DATABASE, ("sqlserver", "mssql")),
    ("SQLite", CATEGORY_DATABASE, ()),
    ("Redis", CATEGORY_DATABASE, ()),
    ("MongoDB", CATEGORY_DATABASE, ("mongo",)),
    ("Elasticsearch", CATEGORY_DATABASE, ("es", "elastic search")),
    ("ClickHouse", CATEGORY_DATABASE, ()),
    ("HBase", CATEGORY_DATABASE, ()),
    ("Cassandra", CATEGORY_DATABASE, ()),
    ("Neo4j", CATEGORY_DATABASE, ()),
    ("Milvus", CATEGORY_DATABASE, ()),
    ("pgvector", CATEGORY_DATABASE, ()),
    ("SQL优化", CATEGORY_DATABASE, ("慢查询", "索引优化", "sql调优")),
    ("分库分表", CATEGORY_DATABASE, ("sharding", "读写分离")),
    ("事务", CATEGORY_DATABASE, ("transaction", "acid")),
    # 中间件
    ("Kafka", CATEGORY_MIDDLEWARE, ("apache kafka",)),
    ("RabbitMQ", CATEGORY_MIDDLEWARE, ("rabbit mq",)),
    ("RocketMQ", CATEGORY_MIDDLEWARE, ("rocket mq",)),
    ("ActiveMQ", CATEGORY_MIDDLEWARE, ()),
    ("ZooKeeper", CATEGORY_MIDDLEWARE, ("zookeeper", "zk")),
    ("Nginx", CATEGORY_MIDDLEWARE, ()),
    ("Apache", CATEGORY_MIDDLEWARE, ("apache httpd",)),
    ("Tomcat", CATEGORY_MIDDLEWARE, ()),
    ("Dubbo", CATEGORY_MIDDLEWARE, ()),
    ("Nacos", CATEGORY_MIDDLEWARE, ()),
    ("Sentinel", CATEGORY_MIDDLEWARE, ()),
    ("ETCD", CATEGORY_MIDDLEWARE, ("etcd",)),
    ("Consul", CATEGORY_MIDDLEWARE, ()),
    # 云原生与运维
    ("Docker", CATEGORY_CLOUD, ("容器", "container", "容器化")),
    ("Kubernetes", CATEGORY_CLOUD, ("k8s", "k8s集群")),
    ("Helm", CATEGORY_CLOUD, ()),
    ("Istio", CATEGORY_CLOUD, ()),
    ("Jenkins", CATEGORY_CLOUD, ()),
    ("GitLab CI", CATEGORY_CLOUD, ("gitlab-ci", "gitlab runner")),
    ("GitHub Actions", CATEGORY_CLOUD, ("github action",)),
    ("CI/CD", CATEGORY_CLOUD, ("cicd", "持续集成", "持续交付")),
    ("DevOps", CATEGORY_CLOUD, ()),
    ("Terraform", CATEGORY_CLOUD, ()),
    ("Ansible", CATEGORY_CLOUD, ()),
    ("Prometheus", CATEGORY_CLOUD, ()),
    ("Grafana", CATEGORY_CLOUD, ()),
    ("ELK", CATEGORY_CLOUD, ("elk stack", "logstash", "kibana")),
    ("SkyWalking", CATEGORY_CLOUD, ()),
    ("可观测性", CATEGORY_CLOUD, ("observability", "链路追踪", "监控告警")),
    ("AWS", CATEGORY_CLOUD, ("amazon web services",)),
    ("阿里云", CATEGORY_CLOUD, ("aliyun", "ali cloud")),
    ("腾讯云", CATEGORY_CLOUD, ("tencent cloud",)),
    ("华为云", CATEGORY_CLOUD, ("huawei cloud",)),
    ("Azure", CATEGORY_CLOUD, ("microsoft azure",)),
    ("Google Cloud", CATEGORY_CLOUD, ("gcp",)),
    ("Serverless", CATEGORY_CLOUD, ("serverless架构",)),
    # 大数据
    ("Hadoop", CATEGORY_BIGDATA, ()),
    ("Spark", CATEGORY_BIGDATA, ("apache spark", "spark sql")),
    ("Flink", CATEGORY_BIGDATA, ("apache flink",)),
    ("Hive", CATEGORY_BIGDATA, ()),
    ("Kafka Streams", CATEGORY_BIGDATA, ()),
    ("Airflow", CATEGORY_BIGDATA, ()),
    ("DolphinScheduler", CATEGORY_BIGDATA, ()),
    ("DataX", CATEGORY_BIGDATA, ()),
    ("数据仓库", CATEGORY_BIGDATA, ("数仓", "data warehouse", "dw")),
    ("数据建模", CATEGORY_BIGDATA, ("维度建模", "data modeling")),
    ("ETL", CATEGORY_BIGDATA, ("数据清洗", "数据同步")),
    ("OLAP", CATEGORY_BIGDATA, ("联机分析",)),
    # 人工智能
    ("机器学习", CATEGORY_AI, ("machine learning", "ml")),
    ("深度学习", CATEGORY_AI, ("deep learning", "dl")),
    ("PyTorch", CATEGORY_AI, ("torch",)),
    ("TensorFlow", CATEGORY_AI, ("tf",)),
    ("Keras", CATEGORY_AI, ()),
    ("scikit-learn", CATEGORY_AI, ("sklearn", "scikit learn")),
    ("XGBoost", CATEGORY_AI, ()),
    ("LightGBM", CATEGORY_AI, ()),
    ("NLP", CATEGORY_AI, ("自然语言处理",)),
    ("计算机视觉", CATEGORY_AI, ("cv", "computer vision")),
    ("推荐系统", CATEGORY_AI, ("推荐算法", "recommendation")),
    ("知识图谱", CATEGORY_AI, ("knowledge graph",)),
    ("大模型", CATEGORY_AI, ("llm", "large language model", "大语言模型")),
    ("RAG", CATEGORY_AI, ("检索增强", "retrieval augmented generation")),
    ("Prompt Engineering", CATEGORY_AI, ("提示词工程", "prompt工程")),
    ("Transformer", CATEGORY_AI, ()),
    ("LoRA", CATEGORY_AI, ("微调", "fine-tuning", "finetune")),
    ("LangChain", CATEGORY_AI, ("langchain",)),
    ("向量检索", CATEGORY_AI, ("embedding", "向量数据库", "相似度检索")),
    ("模型部署", CATEGORY_AI, ("模型推理", "model serving", "vllm")),
    ("数据挖掘", CATEGORY_AI, ("data mining",)),
    ("特征工程", CATEGORY_AI, ("feature engineering",)),
    # 测试与质量
    ("单元测试", CATEGORY_TESTING, ("unit test", "unittest")),
    ("pytest", CATEGORY_TESTING, ()),
    ("JUnit", CATEGORY_TESTING, ()),
    ("Selenium", CATEGORY_TESTING, ()),
    ("Playwright", CATEGORY_TESTING, ()),
    ("Cypress", CATEGORY_TESTING, ()),
    ("Jest", CATEGORY_TESTING, ()),
    ("Vitest", CATEGORY_TESTING, ()),
    ("自动化测试", CATEGORY_TESTING, ("test automation", "自动化用例")),
    ("接口测试", CATEGORY_TESTING, ("api测试", "postman")),
    ("性能测试", CATEGORY_TESTING, ("jmeter", "loadrunner", "压测")),
    ("TDD", CATEGORY_TESTING, ("测试驱动开发",)),
    ("代码覆盖率", CATEGORY_TESTING, ("coverage",)),
    # 工具与协作
    ("Git", CATEGORY_TOOLING, ("github", "gitlab", "gitee")),
    ("Linux", CATEGORY_TOOLING, ("ubuntu", "centos", "unix")),
    ("Maven", CATEGORY_TOOLING, ()),
    ("Gradle", CATEGORY_TOOLING, ()),
    ("npm", CATEGORY_TOOLING, ("yarn", "pnpm")),
    ("pip", CATEGORY_TOOLING, ("poetry", "uv")),
    ("Swagger", CATEGORY_TOOLING, ("openapi",)),
    ("Jira", CATEGORY_TOOLING, ("confluence",)),
    ("Postman", CATEGORY_TOOLING, ()),
    ("Vim", CATEGORY_TOOLING, ()),
    ("VS Code", CATEGORY_TOOLING, ("vscode",)),
    ("IntelliJ IDEA", CATEGORY_TOOLING, ("idea", "intellij")),
    # 操作系统与网络
    ("TCP/IP", CATEGORY_SYSTEM, ("tcp", "ip协议", "网络协议")),
    ("HTTP", CATEGORY_SYSTEM, ("http2", "https")),
    ("操作系统", CATEGORY_SYSTEM, ("os", "operating system")),
    ("多线程", CATEGORY_SYSTEM, ("并发编程", "multithreading")),
    ("协程", CATEGORY_SYSTEM, ("coroutine", "asyncio")),
    ("网络编程", CATEGORY_SYSTEM, ("socket",)),
    ("计算机基础", CATEGORY_SYSTEM, ("数据结构", "算法基础")),
    # 软技能
    ("团队协作", CATEGORY_SOFT, ("团队合作", "teamwork")),
    ("沟通能力", CATEGORY_SOFT, ("沟通表达", "communication")),
    ("项目管理", CATEGORY_SOFT, ("project management",)),
    ("需求分析", CATEGORY_SOFT, ("需求评审",)),
    ("技术文档", CATEGORY_SOFT, ("文档编写", "technical writing")),
    ("英文读写", CATEGORY_SOFT, ("英语", "cet-6", "cet6")),
    ("问题排查", CATEGORY_SOFT, ("线上问题", "故障排查", "troubleshooting")),
)


@dataclass(frozen=True)
class SkillEntry:
    """One canonical skill and the surface forms that should resolve to it."""

    canonical_name: str
    category: str
    aliases: tuple[str, ...] = ()

    @property
    def all_terms(self) -> tuple[str, ...]:
        return (self.canonical_name, *self.aliases)


SEED_SKILLS: tuple[SkillEntry, ...] = tuple(
    SkillEntry(canonical_name=name, category=category, aliases=aliases)
    for name, category, aliases in _RAW_SEED
)


@dataclass(frozen=True)
class SkillMention:
    """A skill found in text, with the exact surface form that triggered it."""

    name: str
    category: str
    source_text: str


def _build_term_pattern(term: str) -> str:
    pattern = re.escape(term)
    if term.lower() in AMBIGUOUS_ALIASES:
        return rf"(?<![A-Za-z0-9]){pattern}(?![A-Za-z0-9])(?!\s+[a-z])"
    return rf"(?<![A-Za-z0-9]){pattern}(?![A-Za-z0-9])"


class SkillDictionary:
    """A compiled, case-insensitive matcher over a set of skill entries.

    Terms are matched longest-first so ``Spring Boot`` wins over ``Spring`` and
    ``Next.js`` wins over ``Next``. Later entries never shadow earlier ones for
    the same surface form, which keeps resolution deterministic.
    """

    def __init__(self, entries: Iterable[SkillEntry]) -> None:
        self._entries: list[SkillEntry] = []
        seen_canonical: set[str] = set()
        term_owner: dict[str, SkillEntry] = {}
        for entry in entries:
            if entry.canonical_name in seen_canonical:
                continue
            seen_canonical.add(entry.canonical_name)
            self._entries.append(entry)
            for term in entry.all_terms:
                term_owner.setdefault(term.lower(), entry)
        self._term_owner = term_owner
        self._pattern: re.Pattern[str] | None = None
        if term_owner:
            alternatives = sorted(term_owner, key=len, reverse=True)
            self._pattern = re.compile(
                "|".join(_build_term_pattern(term) for term in alternatives),
                re.IGNORECASE,
            )

    @property
    def entries(self) -> tuple[SkillEntry, ...]:
        return tuple(self._entries)

    @property
    def canonical_names(self) -> tuple[str, ...]:
        return tuple(entry.canonical_name for entry in self._entries)

    def category_of(self, canonical_name: str) -> str | None:
        for entry in self._entries:
            if entry.canonical_name == canonical_name:
                return entry.category
        return None

    def find_mentions(self, text: str) -> list[SkillMention]:
        """Return one mention per canonical skill, in order of first appearance."""

        if self._pattern is None or not text:
            return []
        mentions: list[SkillMention] = []
        seen: set[str] = set()
        for match in self._pattern.finditer(text):
            entry = self._term_owner.get(match.group(0).lower())
            if entry is None or entry.canonical_name in seen:
                continue
            seen.add(entry.canonical_name)
            mentions.append(
                SkillMention(
                    name=entry.canonical_name,
                    category=entry.category,
                    source_text=match.group(0),
                )
            )
        return mentions

    def extended_with(self, overrides: Iterable[SkillEntry]) -> "SkillDictionary":
        """Return a dictionary that unions ``overrides`` into this one.

        Aliases are unioned rather than replaced so that improving the bundled
        seed always takes effect even when the same skill was already imported
        into the database. Category is taken from the override when present,
        which lets an operator recategorise a skill without touching code.
        """

        incoming: dict[str, SkillEntry] = {}
        for entry in overrides:
            existing = incoming.get(entry.canonical_name)
            if existing is None:
                incoming[entry.canonical_name] = entry
                continue
            incoming[entry.canonical_name] = SkillEntry(
                canonical_name=entry.canonical_name,
                category=entry.category,
                aliases=tuple(dict.fromkeys((*existing.aliases, *entry.aliases))),
            )

        combined: list[SkillEntry] = []
        for entry in self._entries:
            override = incoming.pop(entry.canonical_name, None)
            if override is None:
                combined.append(entry)
                continue
            combined.append(
                SkillEntry(
                    canonical_name=entry.canonical_name,
                    category=override.category or entry.category,
                    aliases=tuple(dict.fromkeys((*entry.aliases, *override.aliases))),
                )
            )
        combined.extend(incoming.values())
        return SkillDictionary(combined)


DEFAULT_SKILL_DICTIONARY = SkillDictionary(SEED_SKILLS)
