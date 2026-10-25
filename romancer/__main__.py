from .cli import main

if __name__ == "__main__":
    import os
    rc = main()
    os._exit(int(rc or 0))
