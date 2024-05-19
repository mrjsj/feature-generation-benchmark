import shutil
import sys
from pathlib import Path

import polars as pl
from data_generation.helpers import BenchmarkWriter, DatasetSizes
from rich import print

# See lib.rs for details about constants
CARD_TYPES = ("DC", "CC")
TRANSACTION_TYPES = (
    "food-and-household",
    "home",
    "uncategorized",
    "leisure-and-lifestyle",
    "health-and-beauty",
    "shopping-and-services",
    "children",
    "vacation-and-travel",
    "education",
    "insurance",
    "investments-and-savings",
    "expenses-and-other",
    "cars-and-transportation",
)
CHANNELS = ("mobile", "web")


# Required time windows
WINDOWS_IN_DAYS = (
    7,  # week
    14,  # two weeks
    21,  # three weeks
    30,  # month
    90,  # three months
    180,  # half of the year
    360,  # year
    720,  # two years
)


# Information for result
NAME = "Polars pivot"


def generate_pivoted_batch(data: pl.DataFrame, t_minus: int, groups: list[str]) -> pl.DataFrame:
    pivoted = (
        data.filter(pl.col("t_minus") <= t_minus)
        .group_by(["customer_id"] + groups)
        .agg(
            [
                pl.count("trx_amnt").alias("count"),
                pl.mean("trx_amnt").alias("mean"),
                pl.sum("trx_amnt").alias("sum"),
                pl.min("trx_amnt").alias("min"),
                pl.max("trx_amnt").alias("max"),
            ]
        )
        .pivot(index="customer_id", columns=groups, values=["count", "mean", "sum", "min", "max"])
    )

    # Polars make some nasty looking column names when pivoting.
    pivoted = pivoted.rename(
        {
            column: (
                column.split("_")[-1].replace("{", "").replace("}", "").replace('"', "").replace(",", "_")
                + f"_{t_minus}d_"
                + column.split("_")[0]
            )
            for column in pivoted.columns
            if column != "customer_id"
        }
    )
    return pivoted


if __name__ == "__main__":
    path = sys.argv[1]

    if "tiny" in path:
        task_size = DatasetSizes.TINY
    elif "small" in path:
        task_size = DatasetSizes.SMALL
    elif "medium" in path:
        task_size = DatasetSizes.MEDIUM
    else:
        task_size = DatasetSizes.BIG

    shutil.rmtree("tmp_out", ignore_errors=True)

    results_prefix = Path(__file__).parent.parent.joinpath("results")
    helper = BenchmarkWriter(NAME, task_size, results_prefix)

    # Start the work
    helper.before()

    data = pl.read_parquet(path + "/**/*.parquet")

    #  #   Column       Dtype
    # ---  ------       -----
    #  0   customer_id  int64
    #  1   card_type    object
    #  2   trx_type     object
    #  3   channel      object
    #  4   trx_amnt     float64
    #  5   t_minus      int64
    #  6   part_col     category

    dfs_list: list[pl.DataFrame] = []

    for win in WINDOWS_IN_DAYS:
        # Iterate over combination card_type + trx_type
        dfs_list.append(generate_pivoted_batch(data, win, ["card_type", "trx_type"]))

        # Iterate over combination channel + trx_type
        dfs_list.append(generate_pivoted_batch(data, win, ["channel", "trx_type"]))

    (pl.concat(dfs_list, how="align").write_parquet("../tmp_out"))

    total_time = helper.after()
    print(f"[italic green]Total time: {total_time} seconds[/italic green]")
    sys.exit(0)
