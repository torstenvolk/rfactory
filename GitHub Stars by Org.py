import streamlit as st
import requests
import csv
import os
from datetime import datetime, timedelta, date
import matplotlib.pyplot as plt
import numpy as np

import matplotlib.dates as mdates

# Your GitHub personal access token
github_token = st.secrets["github"]["github_api_key"]

headers = {
    "Authorization": f"Bearer {github_token}",
    "Content-Type": "application/json",
}

url = "https://api.github.com/graphql"

# Define the GraphQL query for fetching stargazers outside of fetch_stargazers function
stargazers_query = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    nameWithOwner
    stargazers(first: 100, after: $cursor) {
      pageInfo {
        endCursor
        hasNextPage
      }
      edges {
        starredAt
      }
    }
  }
}
"""


# Function to fetch top repositories of an organization
def fetch_top_repos(org):
    query = """
    query($org: String!, $first: Int!) {
      organization(login: $org) {
        repositories(first: $first, orderBy: {field: STARGAZERS, direction: DESC}) {
          nodes {
            name
            stargazerCount
          }
        }
      }
    }
    """
    variables = {"org": org, "first": 10}
    response = requests.post(url, json={"query": query, "variables": variables}, headers=headers)

    # Check if the response contains data
    if response.status_code == 200:
        response_json = response.json()
        repos = response_json["data"]["organization"]["repositories"]["nodes"]
        return repos
    else:
        st.error("Error fetching repositories. Please check your GitHub token and organization name.")
        return []

def fetch_stargazers(owner, name, last_fetched_date=None):
    has_next_page = True
    cursor = None
    stargazers = []

    # Streamlit progress feedback
    progress_bar = st.progress(0)
    progress_text = st.empty()
    progress_counter = 0

    while has_next_page:
        st.write(f"Last fetched date for {name}: {last_fetched_date}")

        variables = {"owner": owner, "name": name, "cursor": cursor}
        response = requests.post(url, json={"query": stargazers_query, "variables": variables}, headers=headers)
        response_json = response.json()
        data = response_json["data"]["repository"]["stargazers"]

        for edge in data["edges"]:
            star_date = datetime.strptime(edge["starredAt"], "%Y-%m-%dT%H:%M:%SZ")
            # Convert star_date to a date object for comparison
            if last_fetched_date and star_date.date() <= last_fetched_date:
                has_next_page = False
                break  # Break early if a stargazer was added on or before the last fetched date
            stargazers.append({"starredAt": edge["starredAt"]})

        if has_next_page:  # Only update cursor and progress if continuing to fetch
            cursor = data["pageInfo"]["endCursor"]
            has_next_page = data["pageInfo"]["hasNextPage"]

            # Update progress feedback
            progress_counter += len(data["edges"])
            progress_bar.progress(min(progress_counter / 100, 1))  # Adjust progress calculation as needed
            progress_text.text(f"Fetching stargazers: {len(stargazers)} stars fetched so far")

    # Reset progress feedback once fetching is complete
    progress_bar.empty()
    progress_text.empty()

    return [datetime.strptime(star["starredAt"], "%Y-%m-%dT%H:%M:%SZ") for star in stargazers]


def read_csv(csv_file_name):
    star_dates = []
    if os.path.isfile(csv_file_name):
        with open(csv_file_name, newline='') as csvfile:
            reader = csv.reader(csvfile, delimiter=",")
            # Ensure conversion to datetime.date
            star_dates = [datetime.strptime(row[0], "%Y-%m-%d").date() for row in reader]
    return star_dates


def write_csv(csv_file_name, star_dates):
    with open(csv_file_name, mode="w", newline='') as csvfile:
        writer = csv.writer(csvfile)
        for star_date in star_dates:
            writer.writerow([star_date.strftime("%Y-%m-%d")])


def get_first_star_date(owner, name):
    stargazers = fetch_stargazers(owner, name)
    if stargazers:
        return min(stargazers).date()
    return None

def count_stars_by_date(star_dates, days_ago):
    star_counts = [0] * len(days_ago)
    index = 0
    for i, day in enumerate(days_ago):
        while index < len(star_dates) and star_dates[index] <= day:
            index += 1
        star_counts[i] = index
    return star_counts




# Streamlit UI
org_name = st.text_input("Enter the organization name:")
if org_name:
    repos_to_fetch = fetch_top_repos(org_name)

    # Initialize an empty dictionary to store star data for all repos
    repo_star_data = {}

    # Determine the global date range across all repositories
    global_earliest_date = datetime.now().date() - timedelta(days=365)  # Default to one year ago
    global_latest_date = datetime.now().date()

    # Loop through each repository to fetch and process star data
    for repo in repos_to_fetch:
        name = repo['name']
        csv_file_name = f"{org_name}_{name}.csv"

        star_dates = read_csv(csv_file_name)
        if not star_dates:  # If no star data found, fetch it
            new_stargazers = fetch_stargazers(org_name, name)
            star_dates = [star.date() for star in new_stargazers]
            write_csv(csv_file_name, star_dates)

        if star_dates:
            repo_star_data[name] = star_dates
            global_earliest_date = min(global_earliest_date, min(star_dates))
            global_latest_date = max(global_latest_date, max(star_dates))

    # Now, prepare the plotting data
    # Create the figure and axis
    fig, ax = plt.subplots(figsize=(12, 6))

    # Generate the global date range as a list of datetime.date objects
    num_days = (global_latest_date - global_earliest_date).days
    global_date_range = [global_earliest_date + timedelta(days=x) for x in range(num_days + 1)]

    # Prepare data for stacked area chart
    all_star_counts = []
    labels = []

    for name, star_dates in repo_star_data.items():
        # Convert star_dates to datetime.date objects if necessary
        star_dates_np = np.array([d if isinstance(d, date) else d.date() for d in star_dates])

        # Count stars for each date in the global date range
        star_counts = [np.sum(star_dates_np <= d) for d in global_date_range]
        all_star_counts.append(star_counts)
        labels.append(name)

    # Plot as a stacked area chart
    if all_star_counts:
        ax.stackplot(global_date_range, *all_star_counts, labels=labels)
        ax.set_xlim([global_earliest_date, global_latest_date])
        ax.set_xlabel("Date")
        ax.set_ylabel("Cumulative Stars")
        ax.set_title(f"GitHub Stars Over Time for {org_name}'s Repositories")
        ax.legend(loc='upper left')
        st.pyplot(fig)
    else:
        st.write("No star data available to plot.")


