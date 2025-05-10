---
sidebar_position: 1
---

# Installation Guide

## System Requirements

- Python 3.8 or higher
- Git
- Poetry (Python package management tool)
- Optional: Redis server (for certain advanced features)

## Deployment Steps

### 1. Get the Project Code

```bash
# Clone the repository
git clone https://github.com/zifox666/xiaobawang.git

# Enter the project directory
cd xiaobawang
```

### 2. Install Dependencies

```bash
# Install Poetry (if not already installed)
pip install poetry

# Use Poetry to install project dependencies
poetry install
```

### 3. Configure the Project

Copy the environment configuration file:

`cp .env.dev .env.prod`

Edit the `.env.prod` file according to the [Configuration Guide](./configuration.md).

### 4. Start the Service

```bash
poetry run python bot.py
```