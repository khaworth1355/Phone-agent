"""
Routing Engine - Hybrid AI + Keyword + Menu routing system
Determines which department to route caller to based on conversation
"""
import re
from typing import Optional, Dict, List
from dataclasses import dataclass
from database import get_session, Department, RoutingRule


@dataclass
class RoutingDecision:
    """Result of routing analysis"""
    department: str
    department_id: int
    phone_number: str
    method: str  # 'ai_analysis', 'keyword_match', 'menu_selection'
    confidence: float  # 0.0 - 1.0
    reason: str
    needs_confirmation: bool


class RoutingEngine:
    """Hybrid routing engine using keywords, AI, and menu fallback"""

    def __init__(self):
        self.confidence_threshold = 0.8  # AI must be >80% confident to auto-route
        self.menu_fallback_enabled = True

    def determine_route(self, user_text: str, conversation_history: list) -> RoutingDecision:
        """
        Main routing logic: Try Keywords → AI → Menu

        Args:
            user_text: Latest user utterance
            conversation_history: Full conversation for context

        Returns:
            RoutingDecision with department and confidence
        """
        print(f"[RoutingEngine] Analyzing: '{user_text}'")

        # 1. Try keyword matching first (fast and reliable)
        keyword_match = self.check_keyword_rules(user_text)
        if keyword_match and keyword_match.confidence >= 0.9:
            print(f"[RoutingEngine] ✓ High-confidence keyword match: {keyword_match.department}")
            return keyword_match

        # 2. Use AI for intelligent analysis (future Phase 3 enhancement)
        # ai_decision = self.ai_analyze_intent(user_text, conversation_history)
        # if ai_decision and ai_decision.confidence >= self.confidence_threshold:
        #     print(f"[RoutingEngine] ✓ AI routing: {ai_decision.department} ({ai_decision.confidence})")
        #     return ai_decision

        # 3. Fall back to keyword if AI uncertain
        if keyword_match:
            print(f"[RoutingEngine] ✓ Keyword fallback: {keyword_match.department}")
            return keyword_match

        # 4. Present menu as last resort
        if self.menu_fallback_enabled:
            print(f"[RoutingEngine] → Presenting menu (no clear match)")
            return self.present_menu()

        # 5. Default to Sales if all else fails
        return self.get_default_route()

    def check_keyword_rules(self, text: str) -> Optional[RoutingDecision]:
        """
        Check database routing rules for keyword matches
        Returns highest priority match

        Args:
            text: User's text to check for keywords

        Returns:
            RoutingDecision if match found, None otherwise
        """
        text_lower = text.lower()
        session = get_session()

        try:
            # Get active rules ordered by priority (highest first)
            rules = session.query(RoutingRule).filter_by(
                active=True
            ).order_by(
                RoutingRule.priority.desc()
            ).all()

            for rule in rules:
                matched_keywords = []

                for keyword in rule.keywords:
                    # Use word boundaries for exact matching
                    pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
                    if re.search(pattern, text_lower):
                        matched_keywords.append(keyword)

                # Check if match criteria met
                if rule.match_type == 'any' and len(matched_keywords) > 0:
                    # Any keyword matches
                    dept = rule.department
                    return RoutingDecision(
                        department=dept.name,
                        department_id=dept.id,
                        phone_number=dept.phone_number,
                        method='keyword_match',
                        confidence=0.95,  # High confidence for keyword
                        reason=f"Matched keywords: {', '.join(matched_keywords)}",
                        needs_confirmation=False
                    )
                elif rule.match_type == 'all' and len(matched_keywords) == len(rule.keywords):
                    # All keywords must match
                    dept = rule.department
                    return RoutingDecision(
                        department=dept.name,
                        department_id=dept.id,
                        phone_number=dept.phone_number,
                        method='keyword_match',
                        confidence=0.98,  # Very high confidence
                        reason=f"Matched all keywords: {', '.join(matched_keywords)}",
                        needs_confirmation=False
                    )

            return None

        finally:
            session.close()

    def present_menu(self) -> RoutingDecision:
        """
        Return a menu presentation decision
        This triggers the AI to read out department options
        """
        return RoutingDecision(
            department='MENU',
            department_id=0,
            phone_number='',
            method='menu_selection',
            confidence=1.0,
            reason='Presenting menu options to caller',
            needs_confirmation=False
        )

    def get_default_route(self) -> RoutingDecision:
        """Default route when nothing else matches (usually Sales)"""
        session = get_session()

        try:
            dept = session.query(Department).filter_by(name='Sales', active=True).first()

            if dept:
                return RoutingDecision(
                    department=dept.name,
                    department_id=dept.id,
                    phone_number=dept.phone_number,
                    method='default',
                    confidence=0.5,
                    reason='Default routing (no clear match)',
                    needs_confirmation=True
                )

            # Ultimate fallback if Sales dept not found
            return RoutingDecision(
                department='General',
                department_id=0,
                phone_number='+18166741783',
                method='default',
                confidence=0.5,
                reason='System default',
                needs_confirmation=True
            )

        finally:
            session.close()

    def get_department_by_name(self, department_name: str) -> Optional[Department]:
        """
        Get department by name

        Args:
            department_name: Department name (e.g., 'Sales', 'Support')

        Returns:
            Department object or None
        """
        session = get_session()

        try:
            dept = session.query(Department).filter_by(
                name=department_name,
                active=True
            ).first()
            return dept
        finally:
            session.close()

    def _format_history(self, history: list) -> str:
        """Format conversation history for AI prompt"""
        formatted = []
        for msg in history[-5:]:  # Last 5 messages
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            formatted.append(f"{role.title()}: {content}")
        return "\n".join(formatted)


# Global instance
routing_engine = RoutingEngine()
