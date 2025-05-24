#TYPER CLI

import typer
import uvicorn
import subprocess
import sys
import shlex

cli = typer.Typer()

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
DEFAULT_WORKERS = 1

@cli.command()
def run_api(
    host: str = typer.Option(DEFAULT_HOST, help="Host address to bind the API server."),
    port: int = typer.Option(DEFAULT_PORT, help="Port to run the API server on."),
    reload: bool = typer.Option(True, help="Enable auto-reload (for development)."),
    workers: int = typer.Option(DEFAULT_WORKERS, help="Number of Uvicorn workers (if reload is False).")
):
    """Starts the FastAPI API server using Uvicorn."""
    typer.echo(f"Starting API server on {host}:{port} via app.main:app ...")
    try:
        # This tells uvicorn to look for the 'app' object in the 'app.main' module
        uvicorn.run("app.main:app", host=host, port=port, reload=reload, workers=workers if not reload else None)
    except KeyboardInterrupt:
         typer.echo("API server stopped.")
         sys.exit(0)
    except Exception as e:
         typer.echo(f"Error starting API server: {e}", err=True)
         sys.exit(1)

@cli.command()
def run_worker(
    loglevel: str = typer.Option("info", help="Logging level (debug, info, warning, error, critical)."),
    concurrency: int = typer.Option(None, help="Number of worker processes/threads."),
    queues: str = typer.Option("celery,default,supply_chain_tasks", help="Comma-separated list of queues to consume.") # Updated default
):
    """Starts a Celery worker."""
    typer.echo(f"Starting Celery worker (consuming queues: {queues})...")
    command_parts = [
        sys.executable, "-m", "celery", "-A", "tasks.celery_app", "worker",
        f"--loglevel={loglevel}", "-Q", queues
    ]
    if concurrency:
        command_parts.extend([f"--concurrency={concurrency}"])

    try:
         process = subprocess.run(command_parts, check=True)
    except subprocess.CalledProcessError as e:
         typer.echo(f"Celery worker failed with exit code {e.returncode}.", err=True)
         sys.exit(e.returncode)
    except KeyboardInterrupt:
         typer.echo("Celery worker stopping...")
         sys.exit(0)
    except Exception as e:
         typer.echo(f"Error starting Celery worker: {e}", err=True)
         sys.exit(1)

if __name__ == "__main__":
    cli()