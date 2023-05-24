"""The dataset related data processing logic."""
from contextlib import suppress
from pathlib import Path

import geopandas as gpd
import networkx as nx
import osmnx
import pandas as pd
from tqdm import tqdm

DATASET_PATH = Path(__file__).parent.parent / "data"

CITIES_GRAPHS_PATH = DATASET_PATH / "cities_graphs"

CITIES_GRAPHS_PATH.mkdir(parents=True, exist_ok=True)

PROCESSED_DATASET_PATH = DATASET_PATH / "processed"

PROCESSED_DATASET_PATH.mkdir(parents=True, exist_ok=True)


def load_dataset() -> gpd.GeoDataFrame:
    """
    Load the dataset from the data folder.

    :return: The dataset as a GeoDataFrame.
    """
    dataset_path = DATASET_PATH / "geonames-all-cities-with-a-population-1000.geojson"
    return gpd.read_file(dataset_path)


def get_cities_with_population(
    from_population: int = 1000,
    to_population: int = 1_000_000,
) -> gpd.GeoDataFrame:
    """
    Get the cities with a population between from_population and to_population.

    :param from_population: The minimum population.
    :param to_population: The maximum population.
    :return: The cities with a population between from_population and to_population.
    """
    dataset = load_dataset()
    return dataset[
        (dataset["population"] >= from_population)
        & (dataset["population"] <= to_population)
    ]


def download_city_graph(row: gpd.GeoSeries) -> nx.MultiDiGraph:
    """
    Download the graph of a city.

    :param row: The row of the city.
    :return: The graph of the city.
    """
    name, country_code = row["name"], row["country_code"]
    return osmnx.graph_from_place(f"{name}, {country_code}", network_type="drive")


def write_city_graph(row: gpd.GeoSeries) -> None:
    """
    Write the graph of a city to a file.

    :param row: The row of the city.
    """
    name, country_code, geoname_id = row["name"], row["country_code"], row["geoname_id"]
    graph_path = CITIES_GRAPHS_PATH / f"{geoname_id}_{name}_{country_code}.graphml"
    if not graph_path.exists():
        with suppress(ValueError):
            graph = download_city_graph(row)
            osmnx.save_graphml(graph, graph_path)


def get_city_graph(row: gpd.GeoSeries) -> nx.MultiDiGraph:
    """
    Get the graph of a city.

    :param row: The row of the city.
    :return: The graph of the city.
    """
    name, country_code, geoname_id = row["name"], row["country_code"], row["geoname_id"]
    return osmnx.load_graphml(
        CITIES_GRAPHS_PATH / f"{geoname_id}_{name}_{country_code}.graphml"
    )


def write_cities_graphs() -> None:
    """
    Create the graphs of all the cities in the dataset.

    The graphs are saved in the data/cities_graphs folder.
    """
    cities = get_cities_with_population(
        from_population=100_000,
        to_population=110_000,
    )[["population", "name", "country_code", "geoname_id"]]
    for _, row in tqdm(cities.iterrows()):
        write_city_graph(row)


def iterate_over_downloaded_cities_graphs() -> nx.MultiDiGraph:
    """
    Iterate over the available cities graphs.

    Loads the city graph and returns the :py:class:`nx.MultiDiGraph`
    of the city.

    :return: The graph of the city.
    """
    for city_graph_file in CITIES_GRAPHS_PATH.glob("*.graphml"):
        geoname_id, name, country_code = city_graph_file.stem.split("_")
        yield (
            osmnx.load_graphml(city_graph_file),
            {
                "geoname_id": geoname_id,
                "name": name,
                "country_code": country_code,
            },
        )


def calculate_metrics_for_city_graph(graph: nx.MultiDiGraph, metadata: dict) -> dict:
    """
    Calculate the metrics for a city graph.

    The metrics are:

    - The number of nodes.
    - The number of edges.
    - The number of intersections.
    - The number of intersections with n streets.
    - The proportion of intersections with n streets.

    :param graph: The graph of the city.
    :param metadata: The metadata of the city.
                     E.g. city name, country code, geoname ID.
    """
    graph_projection = osmnx.project_graph(graph)
    nodes_proj = osmnx.graph_to_gdfs(graph_projection, edges=False)
    graph_area_m = nodes_proj.unary_union.convex_hull.area
    stats = osmnx.basic_stats(graph_projection, area=graph_area_m)
    for k, count in stats["streets_per_node_counts"].items():
        stats[f"{k}_way_int_count"] = count
    for k, proportion in stats["streets_per_node_proportions"].items():
        stats[f"{k}_way_int_prop"] = proportion
    stats.pop("streets_per_node_counts")
    stats.pop("streets_per_node_proportions")
    stats["area"] = graph_area_m
    stats.update(metadata)
    return stats


def create_stats_df_for_downloaded_cities_graphs() -> pd.DataFrame:
    """
    Create a dataframe with the stats for the downloaded cities graphs.

    :return: The dataframe with the stats for the downloaded cities graphs.
    """
    stats = [
        calculate_metrics_for_city_graph(graph, metadata)
        for graph, metadata in tqdm(iterate_over_downloaded_cities_graphs())
    ]
    return pd.DataFrame(stats).set_index("geoname_id")


def save_stats_df_for_downloaded_cities_graphs(stats_df: pd.DataFrame) -> None:
    """
    Save the stats dataframe for the downloaded cities graphs.

    :param stats_df: The stats dataframe for the downloaded cities graphs.
    """
    stats_df.to_csv(PROCESSED_DATASET_PATH / "stats.csv")


def load_processed_dataset() -> pd.DataFrame:
    """
    Load the processed dataset.

    :return: The processed dataset.
    """
    return pd.read_csv(PROCESSED_DATASET_PATH / "stats.csv", index_col="geoname_id")
