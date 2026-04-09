"""
Task 8 (Extra Credit): SQLite → Neo4j Migration Script
========================================================
Reads all data from the existing social_network.db SQLite database and
recreates it in Neo4j as nodes and relationships, preserving all data and
connections exactly.

Usage:
    python migrate.py

Make sure your Neo4j instance is running and credentials below are correct
before executing.
"""

import sqlite3
from neo4j import GraphDatabase

# ── Configuration ─────────────────────────────────────────────────────────────
SQLITE_DB   = 'social_network.db'
NEO4J_URI   = 'neo4j+s://e5b3b8fe.databases.neo4j.io'
NEO4J_USER  = 'e5b3b8fe'
NEO4J_PASS  = 'ho4Uwh5vlZjVaaGrAqCg7BEZt1MEFfG1sQBlGVBvptU'


def read_sqlite(db_path: str) -> dict:
    """Step 1: Read all relational data from SQLite."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT id, username, name FROM users")
    users = [dict(row) for row in cur.fetchall()]

    cur.execute("SELECT id, user_id, content, timestamp FROM posts")
    posts = [dict(row) for row in cur.fetchall()]

    cur.execute("SELECT follower_id, followee_id FROM followers")
    follows = [dict(row) for row in cur.fetchall()]

    conn.close()
    print(f"  Read {len(users)} users, {len(posts)} posts, {len(follows)} follow relationships from SQLite.")
    return {"users": users, "posts": posts, "follows": follows}


def migrate_to_neo4j(data: dict, uri: str, user: str, password: str):
    """Steps 2 & 3: Convert and insert into Neo4j, preserving all relationships."""
    driver = GraphDatabase.driver(uri, auth=(user, password))

    with driver.session() as session:
        # ── Constraints (idempotent) ──────────────────────────────────────────
        print("\n[1/4] Ensuring constraints...")
        session.run("""
            CREATE CONSTRAINT unique_user_id IF NOT EXISTS
            FOR (u:User) REQUIRE u.id IS UNIQUE
        """)
        session.run("""
            CREATE CONSTRAINT unique_username IF NOT EXISTS
            FOR (u:User) REQUIRE u.username IS UNIQUE
        """)

        # ── Migrate Users → :User nodes ──────────────────────────────────────
        print(f"[2/4] Migrating {len(data['users'])} users...")
        for u in data['users']:
            session.run("""
                MERGE (user:User {id: $id})
                SET user.username = $username,
                    user.name     = $name
            """, id=u['id'], username=u['username'], name=u['name'])

        # ── Migrate Posts → :Post nodes + [:POSTED] relationships ────────────
        print(f"[3/4] Migrating {len(data['posts'])} posts...")
        for p in data['posts']:
            session.run("""
                MATCH (author:User {id: $user_id})
                MERGE (post:Post {id: $id})
                SET post.content   = $content,
                    post.timestamp = datetime(replace($timestamp, ' ', 'T'))
                MERGE (author)-[:POSTED]->(post)
            """, id=p['id'], user_id=p['user_id'],
                 content=p['content'], timestamp=p['timestamp'])

        # ── Migrate Followers → [:FOLLOWS] relationships ──────────────────────
        print(f"[4/4] Migrating {len(data['follows'])} follow relationships...")
        for f in data['follows']:
            session.run("""
                MATCH (follower:User {id: $follower_id})
                MATCH (followee:User {id: $followee_id})
                MERGE (follower)-[:FOLLOWS]->(followee)
            """, follower_id=f['follower_id'], followee_id=f['followee_id'])

    driver.close()


def verify_migration(data: dict, uri: str, user: str, password: str):
    """Quick sanity check: compare counts between SQLite and Neo4j."""
    driver = GraphDatabase.driver(uri, auth=(user, password))
    print("\n── Verification ─────────────────────────────────────────────────────")
    with driver.session() as session:
        neo4j_users  = session.run("MATCH (u:User)  RETURN count(u)  AS c").single()['c']
        neo4j_posts  = session.run("MATCH (p:Post)  RETURN count(p)  AS c").single()['c']
        neo4j_follows = session.run("MATCH ()-[r:FOLLOWS]->() RETURN count(r) AS c").single()['c']

    print(f"  Users   — SQLite: {len(data['users']):<5} Neo4j: {neo4j_users}")
    print(f"  Posts   — SQLite: {len(data['posts']):<5} Neo4j: {neo4j_posts}")
    print(f"  Follows — SQLite: {len(data['follows']):<5} Neo4j: {neo4j_follows}")

    ok = (
        len(data['users'])  == neo4j_users  and
        len(data['posts'])  == neo4j_posts  and
        len(data['follows']) == neo4j_follows
    )
    print("\n  ✅ Migration successful — all counts match!" if ok
          else "\n  ❌ Count mismatch — check the logs above.")
    driver.close()


if __name__ == '__main__':
    print("=== SQLite → Neo4j Migration ===\n")
    print(f"Source : {SQLITE_DB}")
    print(f"Target : {NEO4J_URI}\n")

    print("[Reading SQLite...]")
    data = read_sqlite(SQLITE_DB)

    print("\n[Writing to Neo4j...]")
    migrate_to_neo4j(data, NEO4J_URI, NEO4J_USER, NEO4J_PASS)

    verify_migration(data, NEO4J_URI, NEO4J_USER, NEO4J_PASS)
    print("\nDone. You can now run app.py against Neo4j.")
