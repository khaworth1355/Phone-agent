"""
Test script to manually insert seed data for routing tables
Run once: python test_insert.py
"""
from database import get_session, Department, RoutingRule

session = get_session()

try:
    # Insert departments
    print("Inserting departments...")
    departments = [
        Department(
            name='Sales',
            phone_number='+18166741783',
            description='New orders, product inquiries, and account upgrades',
            priority=1
        ),
        Department(
            name='Support',
            phone_number='+18166741783',
            description='Technical issues, troubleshooting, and customer support',
            priority=2
        ),
        Department(
            name='Billing',
            phone_number='+18166741783',
            description='Billing questions, payment issues, and account management',
            priority=3
        )
    ]

    for dept in departments:
        session.add(dept)

    session.commit()
    print('✓ Departments added!')

    # Verify departments
    depts = session.query(Department).all()
    print(f'  Found {len(depts)} departments: {[d.name for d in depts]}')

    # Insert routing rules
    print("\nInserting routing rules...")
    sales_dept = session.query(Department).filter_by(name='Sales').first()
    support_dept = session.query(Department).filter_by(name='Support').first()
    billing_dept = session.query(Department).filter_by(name='Billing').first()

    rules = [
        RoutingRule(
            rule_name='Order Keywords',
            keywords=['order', 'purchase', 'buy', 'detergent', 'place order', 'want to order'],
            department_id=sales_dept.id,
            priority=100,
            match_type='any'
        ),
        RoutingRule(
            rule_name='Support Issues',
            keywords=['problem', 'issue', 'broken', 'not working', 'help', 'error', 'fix'],
            department_id=support_dept.id,
            priority=90,
            match_type='any'
        ),
        RoutingRule(
            rule_name='Billing Questions',
            keywords=['bill', 'billing', 'charge', 'payment', 'invoice', 'account'],
            department_id=billing_dept.id,
            priority=80,
            match_type='any'
        )
    ]

    for rule in rules:
        session.add(rule)

    session.commit()
    print('✓ Routing rules added!')

    # Verify routing rules
    rules_count = session.query(RoutingRule).count()
    print(f'  Found {rules_count} routing rules')

    # Display all routing rules
    all_rules = session.query(RoutingRule).order_by(RoutingRule.priority.desc()).all()
    for rule in all_rules:
        print(f'    - {rule.rule_name}: {len(rule.keywords)} keywords → {rule.department.name}')

    print('\n' + '='*60)
    print('✅ Database seeded successfully!')
    print('='*60)

except Exception as e:
    session.rollback()
    print(f'\n❌ Error: {e}')
    import traceback
    traceback.print_exc()

finally:
    session.close()
