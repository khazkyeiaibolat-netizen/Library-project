"""Source data for the demo database.

Books are real titles with their real authors and first-publication years
(Kazakh classics, world classics, and textbooks for an AI / databases
programme). Branch districts are real districts of Kazakh cities; branch phone
numbers, readers and loans are made-up demo records (no real people).
"""

BRANCHES = [
    # name, address, phone  (the first two rows are the examples from the coursework)
    ("Орталық кітапхана", "Астана қаласы, Достық көшесі", "+7 700 111 22 33"),
    ("Сарыарқа филиалы", "Астана қаласы, Сарыарқа ауданы", "+7 700 444 55 66"),
    ("Алматы филиалы", "Алматы қаласы, Әуезов ауданы", "+7 700 777 12 34"),
    ("Шымкент филиалы", "Шымкент қаласы, Әл-Фараби ауданы", "+7 700 888 23 45"),
    ("Қарағанды филиалы", "Қарағанды қаласы, Қазыбек би ауданы", "+7 700 999 34 56"),
]

# title, author, genre, first publication year
BOOKS = [
    # --- Kazakh literature ---
    ("Абай жолы", "Мұхтар Әуезов", "Роман", 1942),
    ("Көшпенділер", "Ілияс Есенберлин", "Тарихи роман", 1969),
    ("Менің атым Қожа", "Бердібек Соқпақбаев", "Повесть", 1957),
    ("Қан мен тер", "Әбдіжәміл Нұрпейісов", "Роман", 1970),
    ("Қилы заман", "Мұхтар Әуезов", "Повесть", 1928),
    ("Қараш-Қараш оқиғасы", "Мұхтар Әуезов", "Әңгіме", 1927),
    ("Еңлік–Кебек", "Мұхтар Әуезов", "Драма", 1917),
    ("Ақбілек", "Жүсіпбек Аймауытов", "Роман", 1927),
    ("Тар жол, тайғақ кешу", "Сәкен Сейфуллин", "Роман", 1927),
    ("Қазақ солдаты", "Ғабит Мүсірепов", "Повесть", 1949),
    ("Өлеңдер жинағы", "Абай Құнанбаев", "Поэзия", 1909),
    ("Қырық мысал", "Ахмет Байтұрсынұлы", "Поэзия", 1909),
    ("Оян, қазақ!", "Міржақып Дулатов", "Поэзия", 1909),
    ("Бақытсыз Жамал", "Міржақып Дулатов", "Роман", 1910),
    ("Қамар сұлу", "Сұлтанмахмұт Торайғыров", "Поэзия", 1910),
    ("Құлагер", "Ілияс Жансүгіров", "Поэзия", 1925),
    ("Қырғыз хрестоматиясы", "Ыбырай Алтынсарин", "Оқулық", 1879),
    ("Аз и Я", "Олжас Сүлейменов", "Ғылыми-көпшілік", 1975),
    # --- World literature ---
    ("Қылмыс пен жаза", "Фёдор Достоевский", "Роман", 1866),
    ("Соғыс және бейбітшілік", "Лев Толстой", "Роман", 1869),
    ("Анна Каренина", "Лев Толстой", "Роман", 1878),
    ("Әкелер мен балалар", "Иван Тургенев", "Роман", 1862),
    ("Шебер мен Маргарита", "Михаил Булгаков", "Роман", 1967),
    ("Евгений Онегин", "Александр Пушкин", "Поэзия", 1833),
    ("Гамлет", "Уильям Шекспир", "Драма", 1603),
    ("Ромео мен Джульетта", "Уильям Шекспир", "Драма", 1597),
    ("Дон Кихот", "Мигель де Сервантес", "Роман", 1605),
    ("Фауст", "Иоганн Вольфганг Гёте", "Драма", 1808),
    ("Ұлы үміттер", "Чарльз Диккенс", "Роман", 1861),
    ("Оливер Твист", "Чарльз Диккенс", "Роман", 1838),
    ("Үш мушкетер", "Александр Дюма", "Роман", 1844),
    ("Робинзон Крузо", "Даниэль Дефо", "Роман", 1719),
    ("Гулливердің саяхаттары", "Джонатан Свифт", "Роман", 1726),
    ("Қария мен теңіз", "Эрнест Хемингуэй", "Повесть", 1952),
    ("Кішкентай ханзада", "Антуан де Сент-Экзюпери", "Повесть", 1943),
    ("1984", "Джордж Оруэлл", "Фантастика", 1949),
    ("Ұлы Гэтсби", "Фрэнсис Скотт Фицджеральд", "Роман", 1925),
    ("Том Сойердің басынан кешкендері", "Марк Твен", "Роман", 1876),
    ("Хоббит", "Джон Р. Р. Толкин", "Фантастика", 1937),
    ("Дюна", "Фрэнк Герберт", "Фантастика", 1965),
    ("Мен — робот", "Айзек Азимов", "Фантастика", 1950),
    ("Алхимик", "Пауло Коэльо", "Роман", 1988),
    ("Шерлок Холмстың шытырман оқиғалары", "Артур Конан Дойл", "Детектив", 1892),
    ("Шығыс экспресіндегі кісі өлімі", "Агата Кристи", "Детектив", 1934),
    ("Уақыттың қысқаша тарихы", "Стивен Хокинг", "Ғылыми-көпшілік", 1988),
    ("Сапиенс", "Юваль Ной Харари", "Ғылыми-көпшілік", 2011),
    ("Космос", "Карл Саган", "Ғылыми-көпшілік", 1980),
    # --- Textbooks: databases, AI, programming ---
    ("Database System Concepts", "Abraham Silberschatz, Henry F. Korth, S. Sudarshan", "Оқулық", 2020),
    ("Fundamentals of Database Systems", "Ramez Elmasri, Shamkant B. Navathe", "Оқулық", 2016),
    ("High Performance MySQL", "Silvia Botros, Jeremy Tinley", "Оқулық", 2021),
    ("Designing Data-Intensive Applications", "Martin Kleppmann", "Оқулық", 2017),
    ("Artificial Intelligence: A Modern Approach", "Stuart Russell, Peter Norvig", "Оқулық", 2020),
    ("Deep Learning", "Ian Goodfellow, Yoshua Bengio, Aaron Courville", "Оқулық", 2016),
    ("Hands-On Machine Learning with Scikit-Learn, Keras and TensorFlow", "Aurélien Géron", "Оқулық", 2022),
    ("Pattern Recognition and Machine Learning", "Christopher M. Bishop", "Оқулық", 2006),
    ("The Elements of Statistical Learning", "Trevor Hastie, Robert Tibshirani, Jerome Friedman", "Оқулық", 2009),
    ("Mathematics for Machine Learning", "Marc Peter Deisenroth, A. Aldo Faisal, Cheng Soon Ong", "Оқулық", 2020),
    ("Introduction to Algorithms", "Thomas H. Cormen, Charles E. Leiserson, Ronald L. Rivest, Clifford Stein", "Оқулық", 2022),
    ("Fluent Python", "Luciano Ramalho", "Оқулық", 2022),
    ("Python for Data Analysis", "Wes McKinney", "Оқулық", 2022),
    ("Clean Code", "Robert C. Martin", "Оқулық", 2008),
    ("The Pragmatic Programmer", "Andrew Hunt, David Thomas", "Оқулық", 1999),
]

# Demo readers. The first two are the readers used in the coursework examples.
READERS = [
    "Айдана Сәрсенова", "Нұрлан Әлиев", "Әлия Нұрғалиева", "Мадина Қасымова",
    "Динара Есімова", "Сымбат Жұмабекова", "Гүлнар Төлеубаева", "Аружан Байжанова",
    "Жансая Омарова", "Томирис Тұрсынбаева", "Ғалия Мырзағалиева", "Камила Рахимова",
    "Ләйла Исмаилова", "Назерке Бекмұратова", "Райхан Серікбаева",
    "Ерлан Мұратов", "Бауыржан Сәкенов", "Дәурен Қуанышев", "Ержан Темірханов",
    "Асылбек Омаров", "Нұрсұлтан Қалиев", "Данияр Ахметов", "Алмас Жақсыбеков",
    "Серік Нұрмағамбетов", "Ринат Каримов", "Тимур Абдуллаев", "Айдос Бектенов",
    "Арман Тілеуханов", "Мирас Сағынтаев", "Жәнібек Оспанов",
]

DEMO_PASSWORDS = {
    "admin": "Admin2026!",
    "librarian": "Library2026!",
    "staff": "Staff2026!",
    "reader": "Reader2026!",
}

# username, role, password key, branch index (0-based) or None, reader index or None
DEMO_USERS = [
    ("admin", "admin", "admin", None, None),
    ("librarian", "librarian", "librarian", None, None),
    ("staff_central", "branch_staff", "staff", 0, None),
    ("staff_saryarka", "branch_staff", "staff", 1, None),
    ("staff_almaty", "branch_staff", "staff", 2, None),
    ("aidana", "reader", "reader", None, 0),
    ("nurlan", "reader", "reader", None, 1),
    ("madina", "reader", "reader", None, 3),
    ("erlan", "reader", "reader", None, 15),
]
