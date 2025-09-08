# NLH Training Simulator (M0)

This repository contains the initial scaffolding for a no‑limit hold'em
training simulator.  The goal of milestone **M0** is to deliver a
playable poker engine and user interface without any solver
integration.  To that end the project includes a FastAPI backend, a
Next.js frontend, a set of documentation files describing the
requirements, and a Makefile to ease development and distribution.

## Getting Started

1. Create a Python virtual environment and install backend dependencies:

   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r backend/requirements.txt
   ```

2. Install Node dependencies for the frontend:

   ```bash
   cd frontend && npm install
   ```

3. Start the backend and frontend in separate terminals:

   ```bash
   make api  # starts FastAPI on port 8000
   make web  # starts Next.js on port 3000
   ```

4. Navigate to `http://localhost:3000` to view the placeholder UI.

## Project Layout

- **backend** – FastAPI application exposing API endpoints.  In M0 it
  includes only a health check; future milestones will implement
  session and hand control.
- **frontend** – Next.js application with two pages: a table stub and a
  settings placeholder.  Tailwind CSS is used for styling.
- **data** – Location for SQLite databases and exported histories.  A
  `.gitkeep` file keeps the directory tracked.
- **adapters** – Thin wrappers around third‑party engines and
  evaluators.  The `pokerkit_adapter.py` module currently contains a
  stub implementation.
- **docs** – Authoritative specification documents provided as
  attachments.  These files define the scope and requirements for the
  project.
- **third_party** – Empty placeholder for future third‑party assets.
- **Makefile** – Convenience targets to run the backend, frontend,
  tests and build a distribution zip.
- **.github/workflows** – CI configuration that runs linting, type
  checking, tests and produces a slim zip artifact.

## Roadmap

The full list of tasks for milestone M0 can be found in
`docs/TASKS-M0.md`.  Development proceeds ticket by ticket, with one
pull request per task, as described in the documentation.