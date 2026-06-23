from pydantic import BaseModel
from typing import Optional

class EnvironmentCreate(BaseModel):
    application_id: str
    env_type: str
    location: Optional[str] = None
    ip: Optional[str] = None
    host: Optional[str] = None
    os: Optional[str] = None
    middleware: Optional[str] = None
    cpu_mem: Optional[str] = None
    storage: Optional[str] = None

class EnvironmentUpdate(BaseModel):
    application_id: Optional[str] = None
    env_type: Optional[str] = None
    location: Optional[str] = None
    ip: Optional[str] = None
    host: Optional[str] = None
    os: Optional[str] = None
    middleware: Optional[str] = None
    cpu_mem: Optional[str] = None
    storage: Optional[str] = None

class RequestCreate(BaseModel):
    type: str
    application_id: Optional[str] = None
    applicant_user_id: int
    reason: str
    # register
    app_name: Optional[str] = None
    dept: Optional[str] = None
    biz_owner: Optional[str] = None
    new_status: Optional[str] = None
    start_plan: Optional[str] = None
    # update
    upd_status: Optional[str] = None
    upd_biz_owner: Optional[str] = None
    upd_end_plan: Optional[str] = None
    upd_start_actual: Optional[str] = None
    # retire
    end_plan: Optional[str] = None
    app_category: Optional[str] = None


class ApplicationUpdate(BaseModel):
    application_name: Optional[str] = None
    department_name: Optional[str] = None
    status: Optional[str] = None
    vendor: Optional[str] = None
    business_owner: Optional[str] = None
    system_owner: Optional[str] = None
    ops_manager: Optional[str] = None
    dev_manager: Optional[str] = None
    start_plan: Optional[str] = None
    start_actual: Optional[str] = None
    end_plan: Optional[str] = None
    end_actual: Optional[str] = None
    app_category: Optional[str] = None


class ConfigurationItemCreate(BaseModel):
    ci_name: str
    ci_type: Optional[str] = None
    environment_id: int
    hostname: Optional[str] = None
    ip_address: Optional[str] = None
    bmc_ip: Optional[str] = None
    os: Optional[str] = None
    os_version: Optional[str] = None
    cpu: Optional[str] = None
    memory: Optional[str] = None
    storage: Optional[str] = None
    vendor: Optional[str] = None
    model: Optional[str] = None
    status: Optional[str] = "active"
    note: Optional[str] = None


class ConfigurationItemUpdate(BaseModel):
    ci_name: Optional[str] = None
    ci_type: Optional[str] = None
    environment_id: Optional[int] = None
    hostname: Optional[str] = None
    ip_address: Optional[str] = None
    bmc_ip: Optional[str] = None
    os: Optional[str] = None
    os_version: Optional[str] = None
    cpu: Optional[str] = None
    memory: Optional[str] = None
    storage: Optional[str] = None
    vendor: Optional[str] = None
    model: Optional[str] = None
    status: Optional[str] = None
    note: Optional[str] = None


class AppDepUpdate(BaseModel):
    migration_status: Optional[str] = None
    migration_due_date: Optional[str] = None
    migration_note: Optional[str] = None


class DashboardSummary(BaseModel):
    status_counts: dict
    category_counts: list
    dept_counts: list
    retiring_soon: list
    pending_requests: int
    env_count: int
    ci_count: int


class BubbleApp(BaseModel):
    application_id: str
    application_name: str
    status: Optional[str] = None
    portfolio_area: Optional[int] = None
    annual_cost_million: Optional[int] = None
    is_infrastructure: Optional[int] = 0
    migration_target_id: Optional[str] = None
    app_category: Optional[str] = None
    vendor: Optional[str] = None
    department_name: Optional[str] = None


class BubbleDependency(BaseModel):
    dependency_id: int
    app_id: str
    depends_on_app_id: str
    dependency_type: Optional[str] = None
    note: Optional[str] = None


class BubbleData(BaseModel):
    apps: list
    dependencies: list


class DemandCreate(BaseModel):
    title: str
    it_class: Optional[str] = None
    category: Optional[str] = None
    domain: Optional[str] = None
    type: Optional[str] = None
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    submitter_user_id: Optional[int] = None
    department_id: Optional[int] = None
    manager_user_id: Optional[int] = None
    system_owner_user_id: Optional[int] = None
    pm_user_id: Optional[int] = None
    description: Optional[str] = None
    portfolio: Optional[str] = None
    program: Optional[str] = None
    change_type: Optional[str] = None
    purpose: Optional[str] = None
    feasibility: Optional[str] = None
    priority: Optional[str] = None
    region: Optional[str] = None
    company: Optional[str] = None
    business_unit: Optional[str] = None
    business_case: Optional[str] = None
    expected_benefit: Optional[str] = None
    target_date: Optional[str] = None
    estimated_cost: Optional[int] = None
    requested_budget: Optional[int] = None
    cost_note: Optional[str] = None
    notes: Optional[str] = None
    stage: Optional[str] = 'draft'


class DemandUpdate(BaseModel):
    title: Optional[str] = None
    it_class: Optional[str] = None
    category: Optional[str] = None
    domain: Optional[str] = None
    type: Optional[str] = None
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    submitter_user_id: Optional[int] = None
    department_id: Optional[int] = None
    manager_user_id: Optional[int] = None
    system_owner_user_id: Optional[int] = None
    pm_user_id: Optional[int] = None
    description: Optional[str] = None
    portfolio: Optional[str] = None
    program: Optional[str] = None
    change_type: Optional[str] = None
    purpose: Optional[str] = None
    feasibility: Optional[str] = None
    priority: Optional[str] = None
    region: Optional[str] = None
    company: Optional[str] = None
    business_unit: Optional[str] = None
    business_case: Optional[str] = None
    expected_benefit: Optional[str] = None
    target_date: Optional[str] = None
    estimated_cost: Optional[int] = None
    requested_budget: Optional[int] = None
    cost_note: Optional[str] = None
    notes: Optional[str] = None
    review_comment: Optional[str] = None
    approval_comment: Optional[str] = None


class DemandStageUpdate(BaseModel):
    stage: str
    reject_reason: Optional[str] = None
    review_comment: Optional[str] = None
    approval_comment: Optional[str] = None


class DemandTaskCreate(BaseModel):
    name: str
    due_date: Optional[str] = None
    assignee_user_id: Optional[int] = None
    priority: Optional[str] = None
    state: Optional[str] = 'open'
    comment: Optional[str] = None
    ai_generated: Optional[int] = 0
    rationale: Optional[str] = None


class DemandTaskUpdate(BaseModel):
    name: Optional[str] = None
    due_date: Optional[str] = None
    assignee_user_id: Optional[int] = None
    priority: Optional[str] = None
    state: Optional[str] = None
    comment: Optional[str] = None


class DemandApplicationCreate(BaseModel):
    application_id: str
    relation_note: Optional[str] = None


class CostPlanCreate(BaseModel):
    fiscal_year: int
    fiscal_period: str
    cost_type: str
    unit_cost: Optional[int] = None
    quantity: Optional[int] = 1
    planned_cost: Optional[int] = None
    actual_cost: Optional[int] = 0
    note: Optional[str] = None


class CostPlanUpdate(BaseModel):
    fiscal_year: Optional[int] = None
    fiscal_period: Optional[str] = None
    cost_type: Optional[str] = None
    unit_cost: Optional[int] = None
    quantity: Optional[int] = None
    planned_cost: Optional[int] = None
    actual_cost: Optional[int] = None
    note: Optional[str] = None


class ProjectCreate(BaseModel):
    demand_id: Optional[str] = None
    title: str
    status: Optional[str] = "pending"
    manager_user_id: Optional[int] = None
    portfolio: Optional[str] = None
    description: Optional[str] = None
    created_date: Optional[str] = None


class CmdbRelCreate(BaseModel):
    parent_table: str
    parent_id: str
    child_table: str
    child_id: str
    relation_type_id: Optional[int] = None
    note: Optional[str] = None


class CmdbRelUpdate(BaseModel):
    note: Optional[str] = None
    relation_type_id: Optional[int] = None
