import csv, os, datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI()

DATA_FILE = "inventory.csv"
SALES_FILE = "sales_history.csv"
LOW_STOCK_THRESHOLD = 5

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# Create CSV files if missing
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id","name","quantity","price","total_investment","sold"])

if not os.path.exists(SALES_FILE):
    with open(SALES_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date","item_id","item_name","sold_quantity","amount"])

# Utility functions
def read_items():
    items = []
    with open(DATA_FILE, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            items.append(row)
    return items

def write_items(items):
    with open(DATA_FILE, "w", newline="") as f:
        fieldnames = ["id","name","quantity","price","total_investment","sold"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(items)

def add_sale_record(item_id, item_name, qty, amount):
    with open(SALES_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.date.today().isoformat(),
            item_id,
            item_name,
            qty,
            round(amount, 2)
        ])

# Frontend mount
app.mount("/static", StaticFiles(directory="./frontend"), name="static")

@app.get("/")
def root():
    return FileResponse("./frontend/index.html")

# CRUD
@app.get("/items")
def get_items():
    return read_items()

@app.get("/items/search")
def search_items(query: str):
    query_lower = query.lower()
    return [item for item in read_items() if query_lower in item["name"].lower() or query_lower in item["id"].lower()]
#Add
@app.post("/items")
def add_item(item: dict):
    if int(item["quantity"]) < 10:
        raise HTTPException(status_code=400, detail="Quantity must be 10 or more")
    if not str(item["price"]).startswith("$"):
        item["price"] = f"${item['price']}"
    price_num = float(item["price"].replace("$",""))
    quantity_num = int(item["quantity"])
    item["total_investment"] = str(round(quantity_num * price_num,2))
    item["sold"] = "0"
    items = read_items()
    next_id = f"{max([int(i['id']) for i in items], default=0)+1:03}" if items else "001"
    item["id"] = next_id
    items.append(item)
    write_items(items)
    return {"message":"Item added","id":next_id}

#update
@app.put("/items/{item_id}")
def update_item(item_id: str, item: dict):
    items = read_items()
    found = False
    for i in items:
        if i["id"] == item_id:
            i["name"] = item.get("name", i["name"])
            i["quantity"] = str(item.get("quantity", i["quantity"]))
            price_str = str(item.get("price", i["price"]))
            if not price_str.startswith("$"):
                price_str = f"${price_str}"
            i["price"] = price_str
            price_num = float(i["price"].replace("$",""))
            quantity_num = int(i["quantity"])
            i["total_investment"] = str(round(quantity_num * price_num,2))
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="Item not found")
    write_items(items)
    return {"message":"Item updated"}
#delete
@app.delete("/items/{item_id}")
def delete_item(item_id: str):
    items = read_items()
    new_items = [i for i in items if i["id"] != item_id]
    if len(new_items) == len(items):
        raise HTTPException(status_code=404, detail="Item not found")
    write_items(new_items)
    return {"message":"Item deleted"}

#sell
@app.post("/items/{item_id}/sell")
def sell_item(item_id: str, data: dict):
    # Check if sold is provided
    if "sold" not in data or str(data["sold"]).strip() == "":
        raise HTTPException(status_code=400, detail="Sold quantity is required")

    #  Convert to integer and validate
    try:
        sold_qty = int(data["sold"])
    except ValueError:
        raise HTTPException(status_code=400, detail="Sold quantity must be a valid integer")

    if sold_qty <= 0:
        raise HTTPException(status_code=400, detail="Sold quantity must be a positive integer")

    # Read inventory
    items = read_items()
    found = False

    for item in items:
        if item["id"] == item_id:
            try:
                current_qty = int(item["quantity"])
            except ValueError:
                raise HTTPException(status_code=500, detail="Invalid inventory quantity")

            # 4. Check stock availability
            if sold_qty > current_qty:
                raise HTTPException(status_code=400, detail=f"Not enough stock. Available: {current_qty}")

            # 5. Update inventory
            try:
                price_per_unit = float(item["price"].replace("$", ""))
            except ValueError:
                raise HTTPException(status_code=500, detail="Invalid item price")

            item["quantity"] = str(current_qty - sold_qty)
            item["sold"] = str(int(item.get("sold", "0")) + sold_qty)
            item["total_investment"] = str(round(float(item["total_investment"]) - sold_qty * price_per_unit, 2))

            # 6. Record the sale
            add_sale_record(item_id, item["name"], sold_qty, sold_qty * price_per_unit)

            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail="Item not found")

    # 7. Save inventory
    write_items(items)

    return {"message": f"{sold_qty} units sold"}


# Analysis
@app.get("/items/analysis")
def items_analysis():
    items = read_items()
    total_items = len(items)
    total_investment = round(sum(float(i["total_investment"]) for i in items),2)
    low_stock_count = sum(1 for i in items if int(i["quantity"]) <= LOW_STOCK_THRESHOLD)
    return {
        "total_items": total_items,
        "total_investment": total_investment,
        "low_stock_count": low_stock_count,
    }

# Sales history 
@app.get("/sales-history")
def sales_history():
    sales = {}
    if os.path.exists(SALES_FILE):
        with open(SALES_FILE, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                date = row["date"]
                qty = int(row["sold_quantity"])
                if date not in sales:
                    sales[date] = 0
                sales[date] += qty
    # Convert to list of dicts sorted by date
    chart_data = [{"date": d, "sold": sales[d]} for d in sorted(sales.keys())]
    return chart_data
