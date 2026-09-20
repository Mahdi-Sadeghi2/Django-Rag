مفاهیمی که برام تازه بودن:
Admonition
descendants
decompose
RAG
Embedding
Vector
Vector Sreach
Cosine Similarity
Semantic Sreach
Retrival
Top-k
Grounding
Hallucination
pgvector
MCP
Idempotency
Hybrid Search
Reranking
Query Expansion
برای یادگیری اینها اول اونها رو به AI دادم و ازش خواستم که به صورت ساده و بامثال این مفاهیم و کاربرد شون رو برام توضیح بده.
از این ویدئو یوتیوب هم کمک گرفتم
https://www.youtube.com/watch?v=1imP4X8fUdA





کجا گیر کردم و چطور از گیر بیرون اومدم؟
کانتینر داکر بالا می‌آمد ولی اتصال ممکن نبود با بررسی بیشتر فهمیدم postgresql داخل داکر و اونی که روی سیستم خودم نصبه هر دو دارن به یک پورت گوش میدن.
برای حلش قسمت ports داخل فایل داکر رو به یه پورت دیگه تغییر دادم.
مشکل بعدی این بود که مستندات متنِ خالی برمیگردوندن.
برای حلش اومد قسمتی به کد اضافه کردم که اگر تعداد کاراکتر کمتر از حدی بود اون قسمت رو نادیده بگیره و بعنوان بخشی از مستندات ذخیره نکنه.
