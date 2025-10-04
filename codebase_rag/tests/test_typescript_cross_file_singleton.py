"""
Test TypeScript singleton pattern across files.
Verifies that instance method calls on objects returned from
factory/singleton methods are detected cross-file.
"""

from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import pytest

from codebase_rag.graph_updater import GraphUpdater
from codebase_rag.services.graph_service import MemgraphIngestor


@pytest.fixture
def ts_singleton_project(temp_repo: Path) -> Path:
    """Set up a TypeScript project with singleton pattern."""
    project_path = temp_repo / "ts_singleton_test"
    project_path.mkdir()

    # storage/Storage.ts - Singleton class
    storage_dir = project_path / "storage"
    storage_dir.mkdir()

    (storage_dir / "Storage.ts").write_text("""
// Singleton pattern in TypeScript
export class Storage {
    private static instance: Storage;
    private data: Record<string, any> = {};

    private constructor() {}

    static getInstance(): Storage {
        if (!Storage.instance) {
            Storage.instance = new Storage();
        }
        return Storage.instance;
    }

    clearAll(): void {
        this.data = {};
    }

    save(key: string, value: any): void {
        this.data[key] = value;
    }

    load(key: string): any {
        return this.data[key];
    }
}
""")

    # controllers/SceneController.ts - Uses Storage singleton
    controllers_dir = project_path / "controllers"
    controllers_dir.mkdir()

    (controllers_dir / "SceneController.ts").write_text("""
import { Storage } from '../storage/Storage';

export class SceneController {
    loadMenuScene(): string {
        // Get singleton instance (cross-file static method call)
        const storage = Storage.getInstance();

        // Call instance methods (cross-file method calls)
        storage.clearAll();
        storage.save('scene', 'menu');
        return storage.load('scene');
    }

    loadGameScene(gameData: any): boolean {
        const storage = Storage.getInstance();
        storage.save('game_data', gameData);
        return true;
    }
}
""")

    # main.ts - Entry point
    (project_path / "main.ts").write_text("""
import { SceneController } from './controllers/SceneController';
import { Storage } from './storage/Storage';

class Application {
    start(): string {
        const controller = new SceneController();
        controller.loadMenuScene();

        // Direct singleton access
        const storage = Storage.getInstance();
        const scene = storage.load('scene');

        controller.loadGameScene(scene);
        return scene;
    }
}

function main(): string {
    const app = new Application();
    return app.start();
}

export { Application, main };
""")

    return project_path


def test_ts_singleton_pattern_cross_file_calls(
    ts_singleton_project: Path, mock_ingestor: MemgraphIngestor
) -> None:
    """
    Test that TypeScript singleton pattern calls work across files.
    This mirrors the Python/Java/JavaScript singleton tests.
    """
    from codebase_rag.parser_loader import load_parsers

    parsers, queries = load_parsers()

    updater = GraphUpdater(
        ingestor=mock_ingestor,
        repo_path=ts_singleton_project,
        parsers=parsers,
        queries=queries,
    )
    updater.run()

    project_name = ts_singleton_project.name

    # Get all CALLS relationships
    actual_calls = [
        c
        for c in cast(MagicMock, mock_ingestor.ensure_relationship_batch).call_args_list
        if c.args[1] == "CALLS"
    ]

    # Convert to comparable format
    found_calls = set()
    for call in actual_calls:
        caller_qn = call.args[0][2]
        callee_qn = call.args[2][2]

        if caller_qn.startswith(f"{project_name}."):
            caller_short = caller_qn[len(project_name) + 1 :]
        else:
            caller_short = caller_qn

        if callee_qn.startswith(f"{project_name}."):
            callee_short = callee_qn[len(project_name) + 1 :]
        else:
            callee_short = callee_qn

        found_calls.add((caller_short, callee_short))

    # Expected cross-file calls
    expected_calls = [
        # From SceneController.loadMenuScene to Storage (cross-file)
        (
            "controllers.SceneController.SceneController.loadMenuScene",
            "storage.Storage.Storage.getInstance",
        ),
        (
            "controllers.SceneController.SceneController.loadMenuScene",
            "storage.Storage.Storage.clearAll",
        ),
        (
            "controllers.SceneController.SceneController.loadMenuScene",
            "storage.Storage.Storage.save",
        ),
        (
            "controllers.SceneController.SceneController.loadMenuScene",
            "storage.Storage.Storage.load",
        ),
        # From SceneController.loadGameScene to Storage
        (
            "controllers.SceneController.SceneController.loadGameScene",
            "storage.Storage.Storage.getInstance",
        ),
        (
            "controllers.SceneController.SceneController.loadGameScene",
            "storage.Storage.Storage.save",
        ),
        # From Application.start to SceneController
        (
            "main.Application.start",
            "controllers.SceneController.SceneController.loadMenuScene",
        ),
        (
            "main.Application.start",
            "controllers.SceneController.SceneController.loadGameScene",
        ),
        # From Application.start to Storage
        ("main.Application.start", "storage.Storage.Storage.getInstance"),
        ("main.Application.start", "storage.Storage.Storage.load"),
        # From main.main to Application.start
        ("main.main", "main.Application.start"),
    ]

    missing_calls = []
    for expected_caller, expected_callee in expected_calls:
        if (expected_caller, expected_callee) not in found_calls:
            missing_calls.append((expected_caller, expected_callee))

    if missing_calls:
        print(f"\n### Missing {len(missing_calls)} expected cross-file calls:")
        for caller, callee in missing_calls:
            print(f"  {caller} -> {callee}")

        print(f"\n### Found {len(found_calls)} calls:")
        for caller, callee in sorted(found_calls):
            print(f"  {caller} -> {callee}")

        pytest.fail(
            f"Missing {len(missing_calls)} TypeScript cross-file calls. "
            f"See output above."
        )

    # Verify minimum calls found
    assert len(found_calls) >= len(expected_calls), (
        f"Expected at least {len(expected_calls)} calls, found {len(found_calls)}"
    )
