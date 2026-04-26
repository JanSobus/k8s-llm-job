from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Result:
    index: int
    success: bool
    status_code: int | None
    duration_ms: float
    error: str | None


def get_percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    rank = int((percentile / 100.0) * len(sorted_values) + 0.999999)
    index = max(rank - 1, 0)
    return round(sorted_values[index], 2)


def post_chat(url: str, message: str, index: int, timeout_seconds: int) -> Result:
    started = time.perf_counter()
    form = urlencode(
        {
            "message": f"{message} #{index}",
            "history": "[]",
            "attached_filename": "",
        }
    ).encode("utf-8")
    request = Request(
        url,
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
            response.read()
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            status_code = response.status
            return Result(
                index=index,
                success=200 <= status_code < 300,
                status_code=status_code,
                duration_ms=duration_ms,
                error=None,
            )
    except HTTPError as exc:
        exc.read()
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        return Result(
            index=index,
            success=False,
            status_code=exc.code,
            duration_ms=duration_ms,
            error=str(exc),
        )
    except (TimeoutError, URLError, OSError) as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        return Result(
            index=index,
            success=False,
            status_code=None,
            duration_ms=duration_ms,
            error=str(exc),
        )


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be >= 1")
    return parsed


def http_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise argparse.ArgumentTypeError("url must be an absolute http(s) URL")
    return value


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send concurrent POST requests to /chat.")
    parser.add_argument("--url", type=http_url, default="http://localhost:8000/chat")
    parser.add_argument("--requests", type=positive_int, default=10)
    parser.add_argument("--concurrency", type=positive_int, default=5)
    parser.add_argument("--message", default="load-test ping")
    parser.add_argument("--timeout-seconds", type=positive_int, default=60)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    max_workers = min(args.concurrency, args.requests)
    results: list[Result] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(post_chat, args.url, args.message, index, args.timeout_seconds)
            for index in range(1, args.requests + 1)
        ]
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda result: result.index)
    failures = [result for result in results if not result.success]
    durations = [result.duration_ms for result in results]
    p50 = get_percentile(durations, 50)
    p95 = get_percentile(durations, 95)

    print(f"Completed {len(results)} POST requests against {args.url}")
    print(f"  Concurrency: {args.concurrency}")
    print(f"  Successes:   {len(results) - len(failures)}")
    print(f"  Failures:    {len(failures)}")
    print(f"  p50:         {p50} ms")
    print(f"  p95:         {p95} ms")

    if failures:
        print()
        print("Failures:")
        for failure in failures:
            print(
                f"  #{failure.index}: status={failure.status_code} error={failure.error}"
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
