"""Seed the database with stores in Fortaleza, CE.

Products and prices are intentionally NOT seeded: they come only from the
scrapers (`GET /scrape` or `python -m services.scraper_service`).
"""

from models import (
    Store,
    SessionLocal,
    init_db,
)


def seed():
    init_db()
    db = SessionLocal()

    # Stores in Fortaleza - CE
    stores = [
        Store(
            name="Pão de Açúcar",
            address="Av. Beira Mar, 1234 - Meireles",
            lat=-3.7280,
            lon=-38.4890,
            cep="60110-120",
            website="https://www.paodeacucar.com"
        ),
        Store(
            name="Sams Club",
            address="Av. Santos Dumont, 3331 - Aldeota",
            lat=-3.7430,
            lon=-38.4870,
            cep="60160-041",
            website="https://www.samsclub.com.br"
        ),
        Store(
            name="Mercadinho São Luiz",
            address="Rua João Bandeira, 456 - Centro",
            lat=-3.7300,
            lon=-38.4900,
            cep="60020-000",
            website="https://mercadinhossaoluiz.com.br"
        ),
        Store(
            name="Cometa",
            address="Av. Barão de Studart, 2000 - Aldeota",
            lat=-3.7350,
            lon=-38.4920,
            cep="60130-002",
            website="https://cometasupermercados.com.br"
        ),
        Store(
            name="Assaí Atacadista",
            address="Av. Oliveira Paiva, 1500 - Cidade dos Funcionários",
            lat=-3.7550,
            lon=-38.4950,
            cep="60822-100",
            website="https://www.assai.com.br"
        ),
        Store(
            name="Atacadão",
            address="Av. Washington Soares, 3500 - Edson Queiroz",
            lat=-3.7700,
            lon=-38.5000,
            cep="60811-341",
            website="https://www.atacadao.com.br"
        ),
        Store(
            # Real branch data comes from services.store_locations, not a placeholder address here
            # (see the note on Store.address in models/store.py) - Carnaúba shares Mercadinho's platform.
            name="Carnaúba Supermercados",
            website="https://carnaubasupermercados.com.br",
        ),
        Store(
            name="Pinheiro Supermercado",
            address="Rua Barão de Studart, 1500 - Aldeota",
            lat=-3.7400,
            lon=-38.4930,
            cep="60120-002",
            website="https://www.lojaonline.pinheirosupermercado.com.br"
        ),
        Store(
            name="Supermercado Lagoa",
            address="Av. Senador Virgílio Távora, 800 - Fátima",
            lat=-3.7350,
            lon=-38.5100,
            cep="60050-250",
            website="https://www.superlagoa.com.br"
        ),
    ]
    known = {name for (name,) in db.query(Store.name)}
    added = [s for s in stores if s.name not in known]  # safe to run again: a store is added once
    db.add_all(added)
    db.commit()
    db.close()
    print(f"Added {len(added)} store(s), {len(stores) - len(added)} already present. "
          "Run a scrape to load real products and prices.")


if __name__ == "__main__":
    seed()
