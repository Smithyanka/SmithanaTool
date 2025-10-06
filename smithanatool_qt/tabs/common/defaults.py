import os

def cpu_default_threads(max_threads=32, min_threads=2):
    n = os.cpu_count() or 4
    return max(min_threads, min(max_threads, n // 2))

HOME = os.path.expanduser("~")

DEFAULTS = {
    "threads": cpu_default_threads(),   # везде одинаково
    "auto_threads": True,
    "cut_out_dir": HOME,
    "stitch_out_dir": HOME,
    "stitch_save_dir": HOME,
    "stitch_pick_dir": HOME,
    "stitch_auto_pick_dir": HOME,
}