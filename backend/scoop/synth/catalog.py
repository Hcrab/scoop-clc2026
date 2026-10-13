"""Fictional ice cream catalog, stores and suppliers for the synthetic world.

All brand names, products and store names are invented for the prototype.
"""

from __future__ import annotations

# (district, store names); district doubles as the store cluster used by CUSUM
DISTRICTS = {
    "Kowloon": ["Mong Kok Central", "Yau Ma Tei", "Kowloon Bay", "Hung Hom", "Tsim Sha Tsui East"],
    "HK Island": ["Causeway Bay", "Wan Chai", "Quarry Bay", "Aberdeen", "Kennedy Town"],
    "NT East": ["Sha Tin Plaza", "Tai Po Market", "Ma On Shan", "Tseung Kwan O", "Fanling"],
    "NT West": ["Tsuen Wan", "Tuen Mun Town", "Yuen Long", "Tin Shui Wai", "Kwai Fong"],
}

DISTRICT_CENTRES = {
    "Kowloon": (22.315, 114.175),
    "HK Island": (22.275, 114.175),
    "NT East": (22.385, 114.205),
    "NT West": (22.390, 114.040),
}

# id, name, lead_time_days, lead_time_sd, order_weekday (0 = Mon)
SUPPLIERS = [
    ("SUP01", "Harbour Chill Foods", 4, 0.8, 0),
    ("SUP02", "Polar Peak Ltd", 6, 1.2, 1),
    ("SUP03", "Lantau Dairy Co", 3, 0.5, 2),
    ("SUP04", "Sunny Isle Frozen", 8, 1.5, 3),
    ("SUP05", "Kowloon Creamery", 5, 1.0, 4),
    ("SUP06", "Jade Garden Sweets", 7, 1.4, 1),
    ("SUP07", "Coastline Gelato", 9, 2.0, 0),
    ("SUP08", "Little Panda Treats", 5, 0.8, 3),
]

BRAND_SUPPLIER = {
    "Harbour Chill": "SUP01",
    "Polar Peak": "SUP02",
    "Lantau Dairy": "SUP03",
    "Sunny Isle": "SUP04",
    "Kowloon Creamery": "SUP05",
    "Jade Garden": "SUP06",
    "Coastline": "SUP07",
    "Little Panda": "SUP08",
}

# name, brand, format, flavours, family, dairy, richness, sweetness, features, health, size_ml, price_hkd
PRODUCTS = [
    ("Mango Splash Ice Bar", "Sunny Isle", "stick", ["mango"], "fruit", 0.05, 0.15, 0.70, [], [], 70, 9.5),
    ("Lychee Frost Bar", "Sunny Isle", "stick", ["lychee"], "fruit", 0.05, 0.10, 0.65, [], [], 70, 9.5),
    ("Watermelon Chill Bar", "Sunny Isle", "stick", ["watermelon"], "fruit", 0.00, 0.10, 0.60, [], ["low_sugar"], 65, 9.0),
    ("Passion Fruit Sorbet Cup", "Coastline", "cup", ["passion_fruit"], "fruit", 0.05, 0.25, 0.65, [], [], 100, 16.0),
    ("Yuzu Lemon Sorbet Cup", "Coastline", "cup", ["citrus"], "fruit", 0.05, 0.20, 0.55, [], ["low_sugar"], 100, 16.0),
    ("Strawberry Burst Bar", "Harbour Chill", "stick", ["strawberry"], "fruit", 0.25, 0.30, 0.75, ["fruit_pieces"], [], 75, 10.0),
    ("Mixed Berry Ice Pop 6-Pack", "Little Panda", "multipack", ["berry"], "fruit", 0.05, 0.10, 0.70, [], [], 300, 32.0),
    ("Tropical Ice Pop 6-Pack", "Little Panda", "multipack", ["mango", "pineapple"], "fruit", 0.05, 0.10, 0.70, [], [], 300, 32.0),
    ("Coconut Water Ice Bar", "Sunny Isle", "stick", ["coconut"], "fruit", 0.15, 0.20, 0.50, [], ["low_sugar"], 70, 10.5),
    ("Mango Sticky Rice Bar", "Jade Garden", "stick", ["mango", "coconut"], "fruit", 0.45, 0.55, 0.75, ["filled"], [], 75, 12.0),
    ("Peach Oolong Ice Bar", "Jade Garden", "stick", ["peach", "tea"], "fruit", 0.10, 0.20, 0.55, [], ["low_sugar"], 70, 11.0),
    ("Pineapple Bun Ice Cream Sandwich", "Kowloon Creamery", "sandwich", ["pineapple", "butter"], "classic", 0.70, 0.75, 0.75, ["crunchy"], [], 90, 14.0),
    ("Raspberry Ripple Tub", "Lantau Dairy", "tub", ["raspberry", "vanilla"], "fruit", 0.80, 0.70, 0.70, [], [], 750, 52.0),
    ("Green Apple Sorbet Tub", "Coastline", "tub", ["apple"], "fruit", 0.05, 0.25, 0.60, [], ["plant_based"], 500, 48.0),
    ("Guava Ice Bar", "Sunny Isle", "stick", ["guava"], "fruit", 0.05, 0.15, 0.65, [], [], 70, 9.5),
    ("Dragon Fruit Smoothie Cup", "Harbour Chill", "cup", ["dragon_fruit"], "fruit", 0.35, 0.35, 0.60, ["fruit_pieces"], [], 120, 15.0),
    ("Classic Choc Crunch Bar", "Polar Peak", "stick", ["chocolate"], "chocolate", 0.85, 0.80, 0.80, ["choc_coated", "crunchy"], [], 90, 13.0),
    ("Double Choc Cone", "Polar Peak", "cone", ["chocolate"], "chocolate", 0.85, 0.85, 0.85, ["choc_coated", "crunchy"], [], 120, 14.5),
    ("Almond Choc Coated Bar", "Polar Peak", "stick", ["chocolate", "almond"], "chocolate", 0.85, 0.90, 0.80, ["choc_coated", "crunchy"], [], 90, 15.0),
    ("Dark Choc Truffle Cup", "Coastline", "cup", ["dark_chocolate"], "chocolate", 0.90, 0.95, 0.70, [], [], 100, 22.0),
    ("Choc Fudge Tub", "Lantau Dairy", "tub", ["chocolate"], "chocolate", 0.90, 0.90, 0.85, [], [], 750, 55.0),
    ("Mini Choc Bites 8-Pack", "Little Panda", "multipack", ["chocolate", "vanilla"], "chocolate", 0.80, 0.80, 0.80, ["choc_coated"], [], 320, 38.0),
    ("Cookies and Cream Sandwich", "Harbour Chill", "sandwich", ["cookies", "vanilla"], "chocolate", 0.80, 0.75, 0.80, ["crunchy"], [], 100, 13.5),
    ("Choc Hazelnut Cone", "Polar Peak", "cone", ["chocolate", "hazelnut"], "chocolate", 0.85, 0.90, 0.85, ["choc_coated", "crunchy"], [], 120, 15.0),
    ("White Choc Raspberry Bar", "Coastline", "stick", ["white_chocolate", "raspberry"], "chocolate", 0.80, 0.85, 0.85, ["choc_coated"], [], 85, 16.0),
    ("Choc Mint Cup", "Lantau Dairy", "cup", ["chocolate", "mint"], "chocolate", 0.80, 0.70, 0.75, [], [], 100, 14.0),
    ("Vanilla Bean Tub", "Lantau Dairy", "tub", ["vanilla"], "classic", 0.90, 0.80, 0.70, [], [], 750, 48.0),
    ("Vanilla Classic Cone", "Polar Peak", "cone", ["vanilla"], "classic", 0.85, 0.70, 0.75, ["crunchy"], [], 120, 12.5),
    ("Milk Ice Bar", "Kowloon Creamery", "stick", ["milk"], "classic", 0.70, 0.50, 0.65, [], [], 70, 8.5),
    ("Vanilla Choc Dip Bar", "Polar Peak", "stick", ["vanilla", "chocolate"], "classic", 0.85, 0.80, 0.80, ["choc_coated"], [], 85, 12.0),
    ("Salted Caramel Cup", "Coastline", "cup", ["caramel"], "classic", 0.85, 0.90, 0.85, [], [], 100, 20.0),
    ("Caramel Swirl Tub", "Lantau Dairy", "tub", ["caramel", "vanilla"], "classic", 0.85, 0.85, 0.85, [], [], 750, 52.0),
    ("Toffee Crunch Cone", "Harbour Chill", "cone", ["toffee"], "classic", 0.80, 0.85, 0.85, ["crunchy", "choc_coated"], [], 120, 13.5),
    ("Hokkaido Milk Soft Cup", "Kowloon Creamery", "cup", ["milk"], "classic", 0.95, 0.75, 0.65, [], [], 110, 17.0),
    ("Vanilla Sandwich", "Harbour Chill", "sandwich", ["vanilla"], "classic", 0.80, 0.70, 0.75, [], [], 90, 11.0),
    ("Light Vanilla Bar", "Harbour Chill", "stick", ["vanilla"], "classic", 0.60, 0.35, 0.40, [], ["low_sugar"], 70, 10.5),
    ("Matcha Red Bean Bar", "Jade Garden", "stick", ["matcha", "red_bean"], "asian", 0.60, 0.55, 0.55, [], [], 75, 11.5),
    ("Uji Matcha Cup", "Jade Garden", "cup", ["matcha"], "asian", 0.80, 0.70, 0.50, [], [], 100, 18.0),
    ("Black Sesame Mochi 6-Pack", "Jade Garden", "mochi", ["black_sesame"], "asian", 0.70, 0.70, 0.60, ["filled"], [], 210, 36.0),
    ("Mango Mochi 6-Pack", "Jade Garden", "mochi", ["mango"], "asian", 0.60, 0.55, 0.70, ["filled"], [], 210, 36.0),
    ("Red Bean Ice Bar", "Kowloon Creamery", "stick", ["red_bean"], "asian", 0.35, 0.40, 0.60, [], [], 70, 8.5),
    ("Taro Milk Cup", "Kowloon Creamery", "cup", ["taro"], "asian", 0.75, 0.65, 0.65, [], [], 100, 13.0),
    ("Milk Tea Bar", "Kowloon Creamery", "stick", ["milk_tea"], "asian", 0.65, 0.55, 0.70, [], [], 75, 9.5),
    ("Hojicha Cone", "Jade Garden", "cone", ["hojicha"], "asian", 0.80, 0.70, 0.55, ["crunchy"], [], 120, 15.0),
    ("Durian Cream Cup", "Jade Garden", "cup", ["durian"], "asian", 0.85, 0.90, 0.70, [], [], 100, 19.0),
    ("Coffee Crunch Bar", "Polar Peak", "stick", ["coffee"], "coffee_nut", 0.80, 0.80, 0.70, ["choc_coated", "crunchy"], [], 85, 13.0),
    ("Espresso Gelato Cup", "Coastline", "cup", ["coffee"], "coffee_nut", 0.80, 0.85, 0.60, [], [], 100, 20.0),
    ("Pistachio Gelato Tub", "Coastline", "tub", ["pistachio"], "coffee_nut", 0.85, 0.90, 0.65, [], [], 500, 62.0),
    ("Peanut Butter Cone", "Harbour Chill", "cone", ["peanut"], "coffee_nut", 0.80, 0.90, 0.80, ["crunchy"], [], 120, 14.0),
    ("Macadamia Cup", "Lantau Dairy", "cup", ["macadamia"], "coffee_nut", 0.85, 0.90, 0.70, [], [], 100, 19.0),
    ("Oat Milk Vanilla Tub", "Coastline", "tub", ["vanilla"], "classic", 0.20, 0.55, 0.55, [], ["plant_based"], 500, 58.0),
    ("Zero Sugar Choc Bar", "Polar Peak", "stick", ["chocolate"], "chocolate", 0.70, 0.60, 0.30, ["choc_coated"], ["low_sugar"], 80, 14.0),
    ("Protein Berry Cup", "Harbour Chill", "cup", ["berry"], "fruit", 0.60, 0.40, 0.35, [], ["low_sugar", "high_protein"], 100, 19.0),
    ("Light Mango Yogurt Bar", "Lantau Dairy", "stick", ["mango", "yogurt"], "fruit", 0.50, 0.35, 0.40, [], ["low_sugar"], 70, 11.0),
    ("Kids Rainbow Pop", "Little Panda", "stick", ["mixed_fruit"], "fruit", 0.05, 0.10, 0.85, [], [], 50, 6.5),
    ("Kids Choc Cone 4-Pack", "Little Panda", "multipack", ["chocolate"], "chocolate", 0.75, 0.70, 0.85, ["crunchy"], [], 280, 30.0),
    ("Mini Milk 10-Pack", "Little Panda", "multipack", ["milk"], "classic", 0.65, 0.45, 0.65, [], [], 350, 28.0),
    ("Family Neapolitan Tub", "Lantau Dairy", "tub", ["vanilla", "chocolate", "strawberry"], "classic", 0.85, 0.75, 0.75, [], [], 1000, 45.0),
    ("Lemon Tea Ice Bar", "Kowloon Creamery", "stick", ["lemon", "tea"], "fruit", 0.05, 0.10, 0.60, [], [], 70, 8.5),
    ("Grapefruit Sorbet Bar", "Coastline", "stick", ["citrus"], "fruit", 0.00, 0.20, 0.50, [], ["low_sugar"], 70, 12.0),
]

FORMAT_BASE_DAILY = {
    "stick": 6.0,
    "cone": 4.5,
    "cup": 3.5,
    "tub": 1.8,
    "multipack": 2.2,
    "sandwich": 3.0,
    "mochi": 2.0,
}

FORMAT_UNITS_PER_CASE = {
    "stick": 40,
    "cone": 24,
    "cup": 24,
    "tub": 6,
    "multipack": 8,
    "sandwich": 24,
    "mochi": 12,
}

# Cases that fit one pallet position in the cold store, by format.
FORMAT_CASES_PER_PALLET = {
    "stick": 60,
    "cone": 40,
    "cup": 48,
    "tub": 80,
    "multipack": 50,
    "sandwich": 48,
    "mochi": 60,
}
