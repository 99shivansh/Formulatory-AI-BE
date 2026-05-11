"""Tool definitions for the support agent."""

import json
from typing import Any, Dict
from loguru import logger

from app.services.ticket_service import get_ticket_service
from app.formulary.service import get_formulary_service


# Define available tools for function calling (OpenAI/Azure format)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_ticket",
            "description": "Create a new support ticket for the user's issue. Use this when the user explicitly asks to create a ticket or when their issue needs to be tracked.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "A brief, clear title summarizing the issue (max 100 chars)"
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed description of the issue including all relevant information the user provided"
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "urgent"],
                        "description": "Priority level based on issue severity. Use 'urgent' for critical issues, 'high' for significant problems, 'medium' for standard issues, 'low' for minor requests."
                    },
                    "category": {
                        "type": "string",
                        "description": "Category of the issue (e.g., 'billing', 'technical', 'account', 'general')"
                    }
                },
                "required": ["title", "description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_ticket",
            "description": "Retrieve details of an existing support ticket by its ID. Use this when the user asks about a specific ticket or wants to check ticket status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "string",
                        "description": "The ticket ID (e.g., 'TKT-ABC12345' or just 'ABC12345')"
                    }
                },
                "required": ["ticket_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_ticket_status",
            "description": "Update the status of an existing ticket. Use this when a ticket needs to be marked as resolved or its status changed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "string",
                        "description": "The ticket ID"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["open", "in_progress", "resolved", "closed"],
                        "description": "New status for the ticket"
                    }
                },
                "required": ["ticket_id", "status"]
            }
        }
    },
    # Formulary Tools
    {
        "type": "function",
        "function": {
            "name": "search_drug",
            "description": "Search for a drug in a formulary plan. If only one plan is uploaded, plan_id can be omitted and it will be auto-detected.",
            "parameters": {
                "type": "object",
                "properties": {
                    "drug_name": {
                        "type": "string",
                        "description": "Name of the drug to search for (e.g., 'Lipitor', 'Metformin')"
                    },
                    "plan_id": {
                        "type": "string",
                        "description": "The formulary plan ID. Optional if only one plan exists."
                    }
                },
                "required": ["drug_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_drug_details",
            "description": "Get detailed information about a drug including access score, insights, and recommendations. Plan auto-detected if only one exists.",
            "parameters": {
                "type": "object",
                "properties": {
                    "drug_name": {
                        "type": "string",
                        "description": "Name of the drug to look up"
                    },
                    "plan_id": {
                        "type": "string",
                        "description": "Optional plan ID. Auto-detected if only one plan exists."
                    }
                },
                "required": ["drug_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "filter_drugs",
            "description": "Filter and count drugs. Use for: 'drugs starting with A', 'count tier 5 drugs'. Plan is auto-detected if only one exists.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name_prefix": {
                        "type": "string",
                        "description": "Filter by name prefix (e.g., 'A' for drugs starting with A)"
                    },
                    "tier": {
                        "type": "number",
                        "description": "Filter by tier 1-6"
                    },
                    "has_restriction": {
                        "type": "string",
                        "description": "Filter by restriction (PA, QL, ST, DL)"
                    },
                    "count_only": {
                        "type": "boolean",
                        "description": "Set to true to only return count"
                    },
                    "plan_id": {
                        "type": "string",
                        "description": "Optional plan ID. Auto-detected if only one plan exists."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_plan_insights",
            "description": "Get analytics and insights for a formulary plan including statistics and recommendations. Plan auto-detected if only one exists.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_id": {
                        "type": "string",
                        "description": "Optional plan ID. Auto-detected if only one plan exists."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_plans",
            "description": "Compare two formulary plans to see which has better drug coverage. Use when user wants to compare insurance plans or find the better option. Do NOT include drug_names parameter unless user specifically mentions drugs to compare.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_a_id": {
                        "type": "string",
                        "description": "First plan ID to compare"
                    },
                    "plan_b_id": {
                        "type": "string",
                        "description": "Second plan ID to compare"
                    }
                },
                "required": ["plan_a_id", "plan_b_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_formulary_plans",
            "description": "List all available formulary plans that have been uploaded. Use this to see what plans are available for querying.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]


# Ollama tools format (compatible with Ollama's native tool calling)
OLLAMA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_ticket",
            "description": "Create a new support ticket for the user's issue. Use this when the user explicitly asks to create a ticket or when their issue needs to be tracked.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "A brief, clear title summarizing the issue (max 100 chars)"
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed description of the issue including all relevant information the user provided"
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "urgent"],
                        "description": "Priority level based on issue severity"
                    },
                    "category": {
                        "type": "string",
                        "description": "Category of the issue (e.g., 'billing', 'technical', 'account', 'general')"
                    }
                },
                "required": ["title", "description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_ticket",
            "description": "Retrieve details of an existing support ticket by its ID. Use this when the user asks about a specific ticket or wants to check ticket status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "string",
                        "description": "The ticket ID (e.g., 'TKT-ABC12345' or just 'ABC12345')"
                    }
                },
                "required": ["ticket_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_ticket_status",
            "description": "Update the status of an existing ticket. Use this when a ticket needs to be marked as resolved or its status changed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "string",
                        "description": "The ticket ID"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["open", "in_progress", "resolved", "closed"],
                        "description": "New status for the ticket"
                    }
                },
                "required": ["ticket_id", "status"]
            }
        }
    },
    # Formulary Tools for Ollama
    {
        "type": "function",
        "function": {
            "name": "search_drug",
            "description": "Search for a drug. Plan auto-detected if only one exists.",
            "parameters": {
                "type": "object",
                "properties": {
                    "drug_name": {"type": "string", "description": "Name of the drug"},
                    "plan_id": {"type": "string", "description": "Optional plan ID"}
                },
                "required": ["drug_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_drug_details",
            "description": "Get detailed drug info. Plan auto-detected if only one exists.",
            "parameters": {
                "type": "object",
                "properties": {
                    "drug_name": {"type": "string", "description": "Name of the drug"},
                    "plan_id": {"type": "string", "description": "Optional plan ID"}
                },
                "required": ["drug_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "filter_drugs",
            "description": "Filter and count drugs. Plan auto-detected if only one exists.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name_prefix": {"type": "string", "description": "Filter by name prefix"},
                    "tier": {"type": "number", "description": "Filter by tier 1-6"},
                    "has_restriction": {"type": "string", "description": "Filter by restriction code"},
                    "count_only": {"type": "boolean", "description": "Return only count if true"},
                    "plan_id": {"type": "string", "description": "Optional plan ID"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_plan_insights",
            "description": "Get plan analytics. Plan auto-detected if only one exists.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_id": {"type": "string", "description": "Optional plan ID"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_plans",
            "description": "Compare two formulary plans. Do NOT include drug_names unless user specifies drugs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_a_id": {"type": "string", "description": "First plan ID"},
                    "plan_b_id": {"type": "string", "description": "Second plan ID"}
                },
                "required": ["plan_a_id", "plan_b_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_formulary_plans",
            "description": "List all available formulary plans.",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]


def _sanitize_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize and normalize tool arguments.
    Handles common issues like strings that should be arrays/objects.
    Removes null values to avoid schema validation errors.
    """
    if arguments is None:
        return {}
    
    if not isinstance(arguments, dict):
        return {}
    
    sanitized = {}
    
    for key, value in arguments.items():
        # Skip null/None values entirely - they cause schema validation errors
        if value is None:
            continue
        elif isinstance(value, str):
            # Try to parse JSON strings that should be arrays or objects
            stripped = value.strip()
            
            # Skip "null" string
            if stripped.lower() == 'null':
                continue
                
            if stripped.startswith('[') or stripped.startswith('{'):
                try:
                    parsed = json.loads(stripped)
                    # Skip empty arrays/objects
                    if parsed == [] or parsed == {}:
                        continue
                    sanitized[key] = parsed
                except json.JSONDecodeError:
                    sanitized[key] = value
            # Skip empty strings
            elif stripped == '' or stripped == '[]' or stripped == '{}':
                continue
            else:
                sanitized[key] = value
        else:
            sanitized[key] = value
    
    return sanitized


def execute_tool(tool_name: str, arguments: Dict[str, Any], conversation_id: str = None) -> str:
    """
    Execute a tool and return the result.
    
    Args:
        tool_name: Name of the tool to execute
        arguments: Tool arguments
        conversation_id: Current conversation ID
        
    Returns:
        Tool execution result as string
    """
    # Sanitize arguments to handle LLM formatting issues
    arguments = _sanitize_arguments(arguments or {})
    
    ticket_service = get_ticket_service()
    formulary_service = get_formulary_service()
    
    try:
        # ==========================================
        # TICKET TOOLS
        # ==========================================
        if tool_name == "create_ticket":
            ticket = ticket_service.create_ticket(
                title=arguments.get("title"),
                description=arguments.get("description"),
                priority=arguments.get("priority", "medium"),
                category=arguments.get("category"),
                conversation_id=conversation_id,
            )
            result = {
                "success": True,
                "ticket_id": ticket.ticket_id,
                "title": ticket.title,
                "status": ticket.status.value,
                "priority": ticket.priority.value,
                "created_at": ticket.created_at.isoformat(),
                "message": f"Ticket {ticket.ticket_id} has been created successfully."
            }
            logger.info(f"Tool executed: create_ticket -> {ticket.ticket_id}")
            
        elif tool_name == "get_ticket":
            ticket = ticket_service.get_ticket(arguments.get("ticket_id"))
            if ticket:
                result = {
                    "success": True,
                    "ticket_id": ticket.ticket_id,
                    "title": ticket.title,
                    "description": ticket.description,
                    "status": ticket.status.value,
                    "priority": ticket.priority.value,
                    "category": ticket.category,
                    "created_at": ticket.created_at.isoformat(),
                    "updated_at": ticket.updated_at.isoformat(),
                }
            else:
                result = {
                    "success": False,
                    "error": f"Ticket not found: {arguments.get('ticket_id')}"
                }
            logger.info(f"Tool executed: get_ticket -> {arguments.get('ticket_id')}")
            
        elif tool_name == "update_ticket_status":
            ticket = ticket_service.update_ticket_status(
                ticket_id=arguments.get("ticket_id"),
                status=arguments.get("status"),
            )
            if ticket:
                result = {
                    "success": True,
                    "ticket_id": ticket.ticket_id,
                    "new_status": ticket.status.value,
                    "message": f"Ticket {ticket.ticket_id} status updated to {ticket.status.value}."
                }
            else:
                result = {
                    "success": False,
                    "error": f"Failed to update ticket: {arguments.get('ticket_id')}"
                }
            logger.info(f"Tool executed: update_ticket_status -> {arguments.get('ticket_id')}")
        
        # ==========================================
        # FORMULARY TOOLS
        # ==========================================
        elif tool_name == "search_drug":
            plan_id = arguments.get("plan_id")
            plan = formulary_service.get_plan(plan_id) if plan_id else None
            
            # Auto-detect plan if plan_id is invalid or not provided
            if not plan:
                all_plans = formulary_service.list_plans()
                if len(all_plans) == 1:
                    plan_id = all_plans[0]["plan_id"]
                    plan = formulary_service.get_plan(plan_id)
                elif len(all_plans) > 1:
                    result = {
                        "success": False,
                        "error": "Multiple plans available. Please specify which plan.",
                        "available_plans": [{"plan_id": p["plan_id"], "plan_name": p["plan_name"]} for p in all_plans]
                    }
                    return json.dumps(result)
                else:
                    result = {"success": False, "error": "No formulary plans uploaded yet."}
                    return json.dumps(result)
            
            plan_name = plan.plan_name
            
            drug = formulary_service.search_drug(
                plan_id=plan_id,
                drug_name=arguments.get("drug_name"),
            )
            if drug:
                result = {
                    "success": True,
                    "plan_name": plan_name,
                    "plan_id": plan_id,
                    "drug_name": drug.drug_name,
                    "form": drug.form,
                    "type": drug.type.value,
                    "tier": drug.tier,
                    "restrictions": drug.restrictions,
                    "restriction_details": drug.restriction_details,
                    "access_score": drug.access_score.score if drug.access_score else None,
                    "access_label": drug.access_score.label.value if drug.access_score else None,
                }
            else:
                result = {
                    "success": False,
                    "error": f"Drug '{arguments.get('drug_name')}' not found in plan '{plan_name}'"
                }
            logger.info(f"Tool executed: search_drug -> {arguments.get('drug_name')}")
            
        elif tool_name == "get_drug_details":
            plan_id = arguments.get("plan_id")
            plan = formulary_service.get_plan(plan_id) if plan_id else None
            
            # Auto-detect plan if plan_id is invalid or not provided
            if not plan:
                all_plans = formulary_service.list_plans()
                if len(all_plans) == 0:
                    result = {
                        "success": False,
                        "error": "No formulary plans uploaded yet. Please upload a formulary PDF first."
                    }
                    return json.dumps(result)
                elif len(all_plans) == 1:
                    plan_id = all_plans[0]["plan_id"]
                    plan = formulary_service.get_plan(plan_id)
                    logger.info(f"Auto-selected plan for get_drug_details: {plan_id}")
                else:
                    result = {
                        "success": False,
                        "error": "Multiple plans available. Please specify which plan.",
                        "available_plans": [{"plan_id": p["plan_id"], "plan_name": p["plan_name"]} for p in all_plans]
                    }
                    return json.dumps(result)
            
            plan_name = plan.plan_name
            
            details = formulary_service.get_drug_details(
                plan_id=plan_id,
                drug_name=arguments.get("drug_name"),
            )
            if details:
                result = {
                    "success": True,
                    "plan_name": plan_name,
                    "plan_id": plan_id,
                    "drug": details.get("drug"),
                    "insights": details.get("insights"),
                    "score_explanation": details.get("score_explanation"),
                }
            else:
                result = {
                    "success": False,
                    "error": f"Drug '{arguments.get('drug_name')}' not found in plan '{plan_name}'"
                }
            logger.info(f"Tool executed: get_drug_details -> {arguments.get('drug_name')}")
            
        elif tool_name == "filter_drugs":
            plan_id = arguments.get("plan_id")
            plan = formulary_service.get_plan(plan_id) if plan_id else None
            
            # Auto-detect plan if plan_id is invalid or not provided
            if not plan:
                all_plans = formulary_service.list_plans()
                if len(all_plans) == 0:
                    result = {
                        "success": False,
                        "error": "No formulary plans uploaded yet. Please upload a formulary PDF first.",
                        "help": "Upload via POST /api/v1/formulary/upload"
                    }
                    return json.dumps(result)
                elif len(all_plans) == 1:
                    # Only one plan exists, use it automatically
                    plan_id = all_plans[0]["plan_id"]
                    plan = formulary_service.get_plan(plan_id)
                    logger.info(f"Auto-selected plan: {plan_id} ({all_plans[0]['plan_name']})")
                elif len(all_plans) > 1:
                    result = {
                        "success": False,
                        "error": "Multiple plans available. Please specify which plan to search.",
                        "available_plans": [{"plan_id": p["plan_id"], "plan_name": p["plan_name"]} for p in all_plans]
                    }
                    return json.dumps(result)
            
            if not plan:
                result = {
                    "success": False,
                    "error": f"Plan not found: {plan_id}"
                }
            else:
                plan_name = plan.plan_name
                raw_prefix = arguments.get("name_prefix")
                name_prefix = (
                    str(raw_prefix).strip().upper()
                    if raw_prefix is not None and str(raw_prefix).strip() != ""
                    else ""
                )
                tier_raw = arguments.get("tier")
                tier_filter = None
                if tier_raw is not None and tier_raw != "":
                    try:
                        tier_filter = int(float(tier_raw))
                    except (TypeError, ValueError):
                        tier_filter = None
                if tier_filter is not None and not (1 <= tier_filter <= 6):
                    tier_filter = None

                has_restriction = arguments.get("has_restriction", "").upper() if arguments.get("has_restriction") else None
                co = arguments.get("count_only", False)
                if isinstance(co, str):
                    count_only = co.strip().lower() in ("true", "1", "yes")
                else:
                    count_only = bool(co)
                
                # Filter drugs
                filtered_drugs = []
                for drug in plan.drugs:
                    display_name = drug.drug_name.strip().upper()
                    # Name prefix filter (strip so leading whitespace/OCR does not break startswith)
                    if name_prefix and not display_name.startswith(name_prefix):
                        continue
                    
                    # Tier filter (coerce LLM number/string/float so int tier matches)
                    if tier_filter is not None and drug.tier != tier_filter:
                        continue
                    
                    # Restriction filter
                    if has_restriction and has_restriction not in drug.restrictions:
                        continue
                    
                    filtered_drugs.append(drug)
                
                if count_only:
                    result = {
                        "success": True,
                        "plan_name": plan_name,
                        "count": len(filtered_drugs),
                        "total_drugs_in_plan": len(plan.drugs),
                        "filter_applied": {
                            "name_prefix": name_prefix or None,
                            "tier": tier_filter,
                            "has_restriction": has_restriction,
                        },
                        "message": f"Found {len(filtered_drugs)} drugs matching criteria out of {len(plan.drugs)} total"
                    }
                else:
                    # Return first 50 drugs to avoid huge responses
                    drug_list = [
                        {
                            "drug_name": d.drug_name,
                            "tier": d.tier,
                            "type": d.type.value,
                            "restrictions": d.restrictions,
                            "access_score": d.access_score.score if d.access_score else None,
                        }
                        for d in filtered_drugs[:50]
                    ]
                    result = {
                        "success": True,
                        "plan_name": plan_name,
                        "count": len(filtered_drugs),
                        "showing": min(50, len(filtered_drugs)),
                        "drugs": drug_list,
                        "message": f"Found {len(filtered_drugs)} drugs" + (f" (showing first 50)" if len(filtered_drugs) > 50 else "")
                    }

                logger.info(
                    f"Tool executed: filter_drugs -> {len(filtered_drugs)} results "
                    f"(prefix={name_prefix!r}, tier={tier_filter})"
                )
            
        elif tool_name == "get_plan_insights":
            plan_id = arguments.get("plan_id")
            plan = formulary_service.get_plan(plan_id) if plan_id else None
            
            # Auto-detect plan if plan_id is invalid or not provided
            if not plan:
                all_plans = formulary_service.list_plans()
                if len(all_plans) == 0:
                    result = {
                        "success": False,
                        "error": "No formulary plans uploaded yet."
                    }
                    return json.dumps(result)
                elif len(all_plans) == 1:
                    plan_id = all_plans[0]["plan_id"]
                    plan = formulary_service.get_plan(plan_id)
                    logger.info(f"Auto-selected plan for insights: {plan_id}")
                else:
                    result = {
                        "success": False,
                        "error": "Multiple plans available. Please specify which plan.",
                        "available_plans": [{"plan_id": p["plan_id"], "plan_name": p["plan_name"]} for p in all_plans]
                    }
                    return json.dumps(result)
            
            plan_name = plan.plan_name
            
            insights = formulary_service.get_plan_insights(plan_id)
            if insights:
                result = {
                    "success": True,
                    "plan_name": plan_name,
                    "plan_id": plan_id,
                    "summary": {
                        "total_drugs": insights.summary.total_drugs,
                        "avg_tier": insights.summary.avg_tier,
                        "pa_percentage": insights.summary.pa_percentage,
                        "avg_access_score": insights.summary.avg_access_score,
                        "high_restriction_drugs": insights.summary.high_restriction_drugs,
                    },
                    "insights": insights.insights,
                    "recommendations": insights.recommendations,
                    "risk_factors": insights.risk_factors,
                }
            else:
                result = {
                    "success": False,
                    "error": f"Plan not found: {plan_id}"
                }
            logger.info(f"Tool executed: get_plan_insights -> {plan_id}")
            
        elif tool_name == "compare_plans":
            # First, check available plans
            all_plans = formulary_service.list_plans()
            
            if len(all_plans) == 0:
                result = {
                    "success": False,
                    "error": "No formulary plans uploaded yet. Please upload plans first."
                }
                return json.dumps(result)
            elif len(all_plans) == 1:
                result = {
                    "success": False,
                    "error": "Only one plan is uploaded. Comparison requires at least 2 different plans.",
                    "available_plan": {"plan_id": all_plans[0]["plan_id"], "plan_name": all_plans[0]["plan_name"]},
                    "suggestion": "Upload another formulary PDF to compare plans."
                }
                return json.dumps(result)
            
            # Get the plan_ids from arguments
            plan_a_id = arguments.get("plan_a_id")
            plan_b_id = arguments.get("plan_b_id")
            
            # Validate plans exist, if not try to match by name
            plan_a = formulary_service.get_plan(plan_a_id)
            plan_b = formulary_service.get_plan(plan_b_id)
            
            # If plans not found by ID, show available plans
            if not plan_a or not plan_b:
                result = {
                    "success": False,
                    "error": "Invalid plan ID(s). Please use the correct plan IDs.",
                    "available_plans": [{"plan_id": p["plan_id"], "plan_name": p["plan_name"]} for p in all_plans],
                    "tip": "Use list_formulary_plans to get valid plan IDs."
                }
                return json.dumps(result)
            
            # Handle drug_names - ensure it's a list or None
            drug_names = arguments.get("drug_names")
            if drug_names is not None:
                if isinstance(drug_names, str):
                    if drug_names.strip() and drug_names.strip() != '[]':
                        try:
                            drug_names = json.loads(drug_names)
                        except:
                            drug_names = [d.strip() for d in drug_names.split(',') if d.strip()]
                    else:
                        drug_names = None
                elif isinstance(drug_names, list) and len(drug_names) == 0:
                    drug_names = None
            
            comparison = formulary_service.compare_plans(
                plan_a_id=plan_a_id,
                plan_b_id=plan_b_id,
                drug_names=drug_names,
            )
            if comparison:
                result = {
                    "success": True,
                    "plan_a_name": comparison.plan_a_name,
                    "plan_b_name": comparison.plan_b_name,
                    "summary": {
                        "better_plan": comparison.summary.better_plan,
                        "plan_a_avg_score": comparison.summary.plan_a_avg_score,
                        "plan_b_avg_score": comparison.summary.plan_b_avg_score,
                        "improvement_percentage": comparison.summary.improvement_percentage,
                        "drugs_better_in_a": comparison.summary.drugs_better_in_a,
                        "drugs_better_in_b": comparison.summary.drugs_better_in_b,
                    },
                    "insights": comparison.insights,
                    "comparison_count": len(comparison.comparison),
                }
            else:
                result = {
                    "success": False,
                    "error": "Failed to compare plans"
                }
            logger.info(f"Tool executed: compare_plans")
            
        elif tool_name == "list_formulary_plans":
            plans = formulary_service.list_plans()
            result = {
                "success": True,
                "plans": plans,
                "count": len(plans),
                "message": f"Found {len(plans)} formulary plan(s)" if plans else "No formulary plans uploaded yet"
            }
            logger.info(f"Tool executed: list_formulary_plans -> {len(plans)} plans")
            
        else:
            result = {"success": False, "error": f"Unknown tool: {tool_name}"}
            logger.warning(f"Unknown tool requested: {tool_name}")
        
        return json.dumps(result)
        
    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {str(e)}")
        return json.dumps({"success": False, "error": str(e)})
