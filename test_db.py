import psycopg2

def run():
    conn = psycopg2.connect("postgresql://lsm_user:lsm_password@localhost:5432/linux_server_manager")
    cur = conn.cursor()
    # Update srv-001 or insert a new one
    sql = """
        INSERT INTO server (server_id, name, hostname, system_uuid, ip_address, os_name, os_version, server_status, organization_id, mqtt_topic)
        VALUES ('1', 'test-server', 'test-server', 'uuid-prod-001', '172.20.0.4', 'Ubuntu', '22.04', 'active', 'default-org', 'zdeploy/test-server/6/1')
        ON CONFLICT (server_id) DO UPDATE SET mqtt_topic = 'zdeploy/test-server/6/1';
    """
    cur.execute(sql)
    conn.commit()
    print("Database updated!")

if __name__ == "__main__":
    run()
