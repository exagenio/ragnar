import threading

def run_in_background(func, *args, **kwargs):
    """background runner"""
    thread = threading.Thread(
        target=func,
        args=args,
        kwargs=kwargs,
        daemon=True
    )
    thread.start()
