"""
Admin API Routes - Manage departments and routing rules via REST API
"""
from flask import Blueprint, request, jsonify, render_template
from functools import wraps
from datetime import datetime, timedelta
from sqlalchemy import func
from database import get_session, Department, RoutingRule, CallRoute, CallTranscript
from config import Config

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# Simple auth decorator
def require_admin_auth(f):
    """Require admin password for protected routes"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.password != Config.ADMIN_PASSWORD:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated


# ==================== DEPARTMENT MANAGEMENT ====================

@admin_bp.route('/departments', methods=['GET'])
@require_admin_auth
def list_departments():
    """GET /admin/departments - List all departments"""
    session = get_session()
    try:
        departments = session.query(Department).order_by(Department.priority.desc()).all()
        return jsonify([{
            'id': d.id,
            'name': d.name,
            'phone_number': d.phone_number,
            'description': d.description,
            'active': d.active,
            'priority': d.priority
        } for d in departments])
    finally:
        session.close()


@admin_bp.route('/departments', methods=['POST'])
@require_admin_auth
def create_department():
    """POST /admin/departments - Create new department"""
    data = request.json

    if not data.get('name') or not data.get('phone_number'):
        return jsonify({'error': 'name and phone_number required'}), 400

    session = get_session()
    try:
        dept = Department(
            name=data['name'],
            phone_number=data['phone_number'],
            description=data.get('description', ''),
            priority=data.get('priority', 0),
            active=data.get('active', True)
        )
        session.add(dept)
        session.commit()
        dept_id = dept.id

        return jsonify({'id': dept_id, 'message': 'Department created'}), 201
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@admin_bp.route('/departments/<int:dept_id>', methods=['PUT'])
@require_admin_auth
def update_department(dept_id):
    """PUT /admin/departments/<id> - Update department"""
    data = request.json
    session = get_session()

    try:
        dept = session.query(Department).get(dept_id)
        if not dept:
            return jsonify({'error': 'Department not found'}), 404

        if 'name' in data:
            dept.name = data['name']
        if 'phone_number' in data:
            dept.phone_number = data['phone_number']
        if 'description' in data:
            dept.description = data['description']
        if 'active' in data:
            dept.active = data['active']
        if 'priority' in data:
            dept.priority = data['priority']

        dept.updated_at = datetime.utcnow()
        session.commit()

        return jsonify({'message': 'Department updated'})
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


# ==================== ROUTING RULES ====================

@admin_bp.route('/routing-rules', methods=['GET'])
@require_admin_auth
def list_routing_rules():
    """GET /admin/routing-rules - List all rules"""
    session = get_session()
    try:
        rules = session.query(RoutingRule).order_by(RoutingRule.priority.desc()).all()
        return jsonify([{
            'id': r.id,
            'rule_name': r.rule_name,
            'keywords': r.keywords,
            'department': r.department.name if r.department else None,
            'department_id': r.department_id,
            'priority': r.priority,
            'active': r.active,
            'match_type': r.match_type
        } for r in rules])
    finally:
        session.close()


@admin_bp.route('/routing-rules', methods=['POST'])
@require_admin_auth
def create_routing_rule():
    """POST /admin/routing-rules - Create new rule"""
    data = request.json

    if not data.get('rule_name') or not data.get('keywords') or not data.get('department_id'):
        return jsonify({'error': 'rule_name, keywords, and department_id required'}), 400

    session = get_session()
    try:
        rule = RoutingRule(
            rule_name=data['rule_name'],
            keywords=data['keywords'],  # Array of strings
            department_id=data['department_id'],
            priority=data.get('priority', 0),
            active=data.get('active', True),
            match_type=data.get('match_type', 'any')
        )
        session.add(rule)
        session.commit()
        rule_id = rule.id

        return jsonify({'id': rule_id, 'message': 'Routing rule created'}), 201
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@admin_bp.route('/routing-rules/<int:rule_id>', methods=['PUT'])
@require_admin_auth
def update_routing_rule(rule_id):
    """PUT /admin/routing-rules/<id> - Update rule"""
    data = request.json
    session = get_session()

    try:
        rule = session.query(RoutingRule).get(rule_id)
        if not rule:
            return jsonify({'error': 'Rule not found'}), 404

        if 'rule_name' in data:
            rule.rule_name = data['rule_name']
        if 'keywords' in data:
            rule.keywords = data['keywords']
        if 'department_id' in data:
            rule.department_id = data['department_id']
        if 'priority' in data:
            rule.priority = data['priority']
        if 'active' in data:
            rule.active = data['active']
        if 'match_type' in data:
            rule.match_type = data['match_type']

        rule.updated_at = datetime.utcnow()
        session.commit()

        return jsonify({'message': 'Rule updated'})
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@admin_bp.route('/routing-rules/<int:rule_id>', methods=['DELETE'])
@require_admin_auth
def delete_routing_rule(rule_id):
    """DELETE /admin/routing-rules/<id> - Deactivate rule"""
    session = get_session()
    try:
        rule = session.query(RoutingRule).get(rule_id)
        if not rule:
            return jsonify({'error': 'Rule not found'}), 404

        rule.active = False
        session.commit()

        return jsonify({'message': 'Rule deactivated'})
    finally:
        session.close()


# ==================== CALL HISTORY ====================

@admin_bp.route('/calls', methods=['GET'])
@require_admin_auth
def list_calls():
    """GET /admin/calls - List recent calls with routing info"""
    limit = request.args.get('limit', 50, type=int)
    session = get_session()

    try:
        calls = session.query(CallRoute).order_by(
            CallRoute.created_at.desc()
        ).limit(limit).all()

        return jsonify([{
            'call_sid': c.call_sid,
            'caller_phone': c.caller_phone,
            'department': c.routing_decision,
            'method': c.routing_method,
            'reason': c.routing_reason,
            'confidence': float(c.confidence_score) if c.confidence_score else None,
            'routed_at': c.routed_at.isoformat() if c.routed_at else None,
            'duration': c.call_duration_seconds,
            'created_at': c.created_at.isoformat()
        } for c in calls])
    finally:
        session.close()


@admin_bp.route('/calls/<call_sid>', methods=['GET'])
@require_admin_auth
def get_call_details(call_sid):
    """GET /admin/calls/<call_sid> - Full transcript and routing details"""
    session = get_session()

    try:
        # Get routing info
        route = session.query(CallRoute).filter_by(call_sid=call_sid).first()
        if not route:
            return jsonify({'error': 'Call not found'}), 404

        # Get transcript
        transcripts = session.query(CallTranscript).filter_by(
            call_sid=call_sid,
            is_final=True
        ).order_by(CallTranscript.timestamp).all()

        return jsonify({
            'call_sid': call_sid,
            'caller_phone': route.caller_phone,
            'department': route.routing_decision,
            'method': route.routing_method,
            'reason': route.routing_reason,
            'confidence': float(route.confidence_score) if route.confidence_score else None,
            'routed_at': route.routed_at.isoformat() if route.routed_at else None,
            'duration': route.call_duration_seconds,
            'transcript': [{
                'timestamp': t.timestamp.isoformat(),
                'speaker': t.speaker,
                'text': t.text
            } for t in transcripts]
        })
    finally:
        session.close()


# ==================== ANALYTICS ====================

@admin_bp.route('/analytics', methods=['GET'])
@require_admin_auth
def get_analytics():
    """GET /admin/analytics - Dashboard metrics"""
    days = request.args.get('days', 30, type=int)
    session = get_session()

    try:
        start_date = datetime.utcnow() - timedelta(days=days)

        # Calls per department
        dept_stats = session.query(
            CallRoute.routing_decision,
            func.count(CallRoute.id).label('count')
        ).filter(
            CallRoute.created_at >= start_date
        ).group_by(CallRoute.routing_decision).all()

        # Average call duration
        avg_duration = session.query(
            func.avg(CallRoute.call_duration_seconds)
        ).filter(
            CallRoute.created_at >= start_date
        ).scalar()

        # Routing method breakdown
        method_stats = session.query(
            CallRoute.routing_method,
            func.count(CallRoute.id).label('count')
        ).filter(
            CallRoute.created_at >= start_date
        ).group_by(CallRoute.routing_method).all()

        # Total calls
        total_calls = session.query(func.count(CallRoute.id)).filter(
            CallRoute.created_at >= start_date
        ).scalar()

        # Calls per day (last 7 days)
        calls_per_day = session.query(
            func.date(CallRoute.created_at).label('date'),
            func.count(CallRoute.id).label('count')
        ).filter(
            CallRoute.created_at >= datetime.utcnow() - timedelta(days=7)
        ).group_by(func.date(CallRoute.created_at)).all()

        return jsonify({
            'period_days': days,
            'total_calls': total_calls or 0,
            'calls_per_department': [{'department': d or 'Unknown', 'count': c} for d, c in dept_stats],
            'avg_call_duration_seconds': float(avg_duration) if avg_duration else 0,
            'routing_methods': [{'method': m or 'Unknown', 'count': c} for m, c in method_stats],
            'calls_per_day': [{'date': str(d), 'count': c} for d, c in calls_per_day]
        })
    finally:
        session.close()


# ==================== TEST ROUTING ====================

@admin_bp.route('/test-route', methods=['POST'])
@require_admin_auth
def test_routing():
    """POST /admin/test-route - Test routing engine with sample text"""
    data = request.json
    text = data.get('text', '')

    if not text:
        return jsonify({'error': 'Text required'}), 400

    from routing_engine import routing_engine
    decision = routing_engine.determine_route(text, [])

    return jsonify({
        'input': text,
        'department': decision.department,
        'method': decision.method,
        'confidence': decision.confidence,
        'reason': decision.reason,
        'needs_confirmation': decision.needs_confirmation
    })


# ==================== DASHBOARD PAGE ====================

@admin_bp.route('/dashboard')
def admin_dashboard():
    """Serve the admin dashboard HTML page"""
    return render_template('admin/dashboard.html')
