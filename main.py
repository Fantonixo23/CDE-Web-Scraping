import os
import pandas as pd
from supabase import create_client
from dotenv import load_dotenv

from stores import nissei, atacado_games, cellshop, visaovip

load_dotenv()

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"],
)

SCRAPERS = [nissei, atacado_games, cellshop, visaovip]
QUERIES = ["iphone", "samsung galaxy", "notebook", "playstation 5", "tv", "audifonos"]


def run_all():
    all_products = []

    for store_module in SCRAPERS:
        for query in QUERIES:
            try:
                results = store_module.scrape(query)
                print(f"{store_module.STORE_ID} / '{query}': {len(results)} productos")
                all_products.extend(results)
            except Exception as e:
                print(f"Error en {store_module.STORE_ID} con '{query}': {e}")

    if not all_products:
        print("No se obtuvo ningún producto en esta corrida.")
        return

    df = pd.DataFrame(all_products)
    df = df.drop_duplicates(subset=["store_origin", "external_id"])
    df["price_updated_at"] = pd.Timestamp.utcnow().isoformat()

    df.to_csv("ultima_corrida.csv", index=False)

    records = df.to_dict(orient="records")

    batch_size = 500
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        supabase.table("products").upsert(batch, on_conflict="store_origin,external_id").execute()

    print(f"{len(records)} productos subidos/actualizados en Supabase.")


if __name__ == "__main__":
    run_all()
