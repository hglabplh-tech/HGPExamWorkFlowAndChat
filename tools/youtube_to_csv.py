"""Search YouTube's official Data API and create a staff-review CSV."""
import argparse
import csv
import os

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("output")
    parser.add_argument("--discipline", required=True)
    parser.add_argument("--course-id", default="")
    parser.add_argument("--max-results", type=int, default=10)
    args = parser.parse_args()
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        raise SystemExit("Set YOUTUBE_API_KEY first")

    response = httpx.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={"part": "snippet", "type": "video", "q": args.query, "maxResults": min(args.max_results, 50), "key": key},
        timeout=30,
    )
    response.raise_for_status()
    fields = ["youtube_url", "youtube_video_id", "title", "description", "discipline", "course_id", "question_tags", "keywords", "staff_approved"]
    with open(args.output, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for item in response.json()["items"]:
            video_id = item["id"]["videoId"]
            snippet = item["snippet"]
            writer.writerow({
                "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
                "youtube_video_id": video_id,
                "title": snippet["title"],
                "description": snippet["description"],
                "discipline": args.discipline,
                "course_id": args.course_id,
                "question_tags": "[]",
                "keywords": "[]",
                "staff_approved": "false",
            })


if __name__ == "__main__":
    main()

