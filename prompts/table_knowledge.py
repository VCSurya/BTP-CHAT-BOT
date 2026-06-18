"""Business-context glossary for the ZHANADB_* schema.

hana_service.introspect_schema() only knows column names, types, and a
few sample rows -- it has no idea what a table is FOR. This file supplies
that missing business knowledge (sourced from the procurement team's data
dictionary) so the planner LLM can pick the right table with confidence
instead of guessing from naming conventions alone.

Keyed by the exact, case-sensitive table name as it appears in HANA.
"importance" is only set for tables the business has flagged as the
central record (the PO master) or as heavily-used in daily operation
(inspection workflow) -- it nudges the planner toward the right table
when a question is ambiguous or broad ("overview", "summary", "give me
everything").
"""

TABLE_BUSINESS_CONTEXT = {
    "ZHANADB_CHANGENOTERECOSET": {
        "purpose": "Stores the recommenders/approvers for Change Notes, tracking who approved a change request and when.",
        "connected_tables": ["ChangeNoteSet", "Users (UserSet)", "CommentSetRecoBy"],
    },
    "ZHANADB_CHANGENOTESET": {
        "purpose": "Main change request/change note management.",
        "connected_tables": ["PurchaseOrders (query.querycv)", "ChangeNoteRecoSet", "CommentSetRecoBy"],
    },
    "ZHANADB_CNAPPROVALSTAGEMASTERSET": {
        "purpose": "Master data for approval stages - stores approver details for each stage.",
        "connected_tables": ["CNApprovalStageMasterSe", "CNPOLimitMasterSet"],
    },
    "ZHANADB_CNAPPROVALTEMPLATESET": {
        "purpose": "Defines approval workflow templates for Change Notes.",
        "connected_tables": ["CNApprovalStageMasterSe", "CNPOLimitMasterSet"],
    },
    "ZHANADB_CNPOLIMITMASTERSET": {
        "purpose": "Master data for PO value limits for approval workflows.",
        "connected_tables": ["CNApprovalTemplateSet"],
    },
    "ZHANADB_CNWF1STAGESET": {
        "purpose": "Tracks current workflow stage for each Change Note.",
        "connected_tables": ["ChangeNoteSet"],
    },
    "ZHANADB_COMMENTSET": {
        "purpose": "Stores comments/remarks linked to any object.",
        "connected_tables": ["PurchaseOrderSet", "CommentSetRecoBy"],
    },
    "ZHANADB_COMMENTSETRECOBY": {
        "purpose": "Stores recommender comments for Change Notes & Service Orders.",
        "connected_tables": ["ChangeNoteSet", "ServiceOrderSet", "CommentSet"],
    },
    "ZHANADB_CONFIGURATION": {
        "purpose": "System configuration settings.",
    },
    "ZHANADB_DOCUMENTMASTERSET": {
        "purpose": "Master data for documents.",
        "connected_tables": ["PurchaseOrders (quality.qualitycv)"],
    },
    "ZHANADB_DOCUMENTSET": {
        "purpose": "Stores document attachments/links.",
        "connected_tables": ["PurchaseOrderSet"],
    },
    "ZHANADB_INSPECTIONITEMSET": {
        "purpose": "Stores inspection item details (quantities, status).",
        "connected_tables": ["InspectionSet", "PurchaseOrders (expediting.expeditingcv)"],
        "importance": "MAINLY IN USE - Contains detailed status and quantity metrics for inspection requests.",
    },
    "ZHANADB_INSPECTIONSET": {
        "purpose": "Main inspection request management.",
        "connected_tables": ["PurchaseOrders (expediting.expeditingcv)", "Users (common.commoncv)", "TPIUsers", "TPISUsers", "MDCCRelationSet", "InspectionItemSet"],
        "importance": "MAINLY IN USE - Tracks overall progress and coordinators of dispatch/quality inspection workflows.",
    },
    "ZHANADB_MATERIALFAMILYSET": {
        "purpose": "Stores material family & sub-family classification.",
        "connected_tables": ["MaterialSet", "PurchaseOrderSet"],
    },
    "ZHANADB_MATERIALSET": {
        "purpose": "Material master data with descriptions.",
        "connected_tables": ["MaterialFamilySet", "PurchaseOrderSet"],
    },
    "ZHANADB_MDCCRELATIONSET": {
        "purpose": "Links MDCC users to inspection requests.",
        "connected_tables": ["InspectionSet"],
    },
    "ZHANADB_MPLMAILCONFIGURATION": {
        "purpose": "Mail/notification configuration for the MPL role.",
    },
    "ZHANADB_NCRDCRDATASET": {
        "purpose": "Main NCR/DCR (Non-Conformance Report/Deviation Control Request) management.",
        "connected_tables": ["PurchaseOrders (query.querycv)", "NCRDCRItemDataSet", "NCRDCRRecoSet"],
    },
    "ZHANADB_NCRDCRITEMDATASET": {
        "purpose": "NCR/DCR item details linked to PO items.",
        "connected_tables": ["PurchaseOrders (query.querycv)", "NCRDCRDataSet"],
    },
    "ZHANADB_NCRDCRRECOSET": {
        "purpose": "Stores recommenders/approvers for NCR/DCR.",
        "connected_tables": ["NCRDCRDataSet", "Users (common.commoncv)"],
    },
    "ZHANADB_POASSIGNMENTSET": {
        "purpose": "Assigns users (TPI, Expeditor, Biller, MPL, PMG, MDCC) to POs.",
        "connected_tables": ["PurchaseOrders (expediting.expeditingcv)", "TPIUsers", "ExpeditorUsers", "BillingUsers", "MplQacUsers", "PmgUsers", "MdccUsers"],
    },
    "ZHANADB_POBGRELATIONSET": {
        "purpose": "Stores Bank Guarantee details linked to POs.",
        "connected_tables": ["PurchaseOrderSet"],
    },
    "ZHANADB_PROJECTWBSSET": {
        "purpose": "Project WBS (Work Breakdown Structure) master data.",
        "connected_tables": ["PurchaseOrderSet"],
    },
    "ZHANADB_PURCHASEORDERSET": {
        "purpose": "Main PO master data - stores all PO details.",
        "connected_tables": ["MaterialSet", "ProjectWBSSet", "WBSTrainSet", "CommentSet", "DocumentSet", "HierarchyNodeSet", "Users (common.commoncv)", "POAssignmentSet", "POBGRelationSet", "MaterialFamilySet"],
        "importance": "MAIN MASTER TABLE - Central hub storing all core purchase order metadata.",
    },
    "ZHANADB_QUERYLISTCONCERNEDSET": {
        "purpose": "Stores concerned persons for queries.",
        "connected_tables": ["QueryListSet"],
    },
    "ZHANADB_QUERYLISTITEMSET": {
        "purpose": "Query items linked to PO items.",
        "connected_tables": ["QueryListSet", "PurchaseOrders (query.querycv)"],
    },
    "ZHANADB_QUERYLISTRECOSET": {
        "purpose": "Stores responders/recommenders for queries.",
        "connected_tables": ["QueryListSet", "Users (common.commoncv)"],
    },
    "ZHANADB_QUERYLISTSET": {
        "purpose": "Main query management.",
        "connected_tables": ["PurchaseOrders (query.querycv)", "QueryListRecoSet", "QueryListConcernedSet", "QueryListItemSet"],
    },
    "ZHANADB_SERVICEORDERDEDUCTIONSET": {
        "purpose": "Stores deduction details for Service Orders.",
        "connected_tables": ["ServiceOrderSet"],
    },
    "ZHANADB_SERVICEORDERRECOMENDERSET": {
        "purpose": "Stores recommenders for Service Orders.",
        "connected_tables": ["ServiceOrderSet", "Users (common.commoncv)"],
    },
    "ZHANADB_SERVICEORDERSET": {
        "purpose": "Main Service Order management.",
        "connected_tables": ["CommentSetRecoBy", "ServiceOrderDeductionSet", "ServiceOrderRecomenderSet"],
    },
    "ZHANADB_TPIRELATIONSET": {
        "purpose": "Maps TPI (Third Party Inspector) to TPIS (Third Party Inspection Service).",
        "connected_tables": ["TPIUsers", "TPISUsers"],
    },
    "ZHANADB_USERROLESET": {
        "purpose": "Maps users to roles (EXPEDITOR, TPI, TPIS, etc.).",
        "connected_tables": ["UserSet"],
    },
    "ZHANADB_USERSET": {
        "purpose": "Main user master data. PRIVATE - contains personal user information.",
        "connected_tables": ["UserRoleSet", "PurchaseOrderSet", "POAssignmentSet", "NCRDCRRecoSet", "QueryListRecoSet", "ServiceOrderRecomenderSet"],
        "importance": "RESTRICTED: never queryable by chat-generated SQL (see RESTRICTED_TABLES in sql_guard.py). Looked up directly, server-side, only for the signed-in user.",
    },
    "ZHANADB_WBS": {
        "purpose": "WBS (Work Breakdown Structure) master.",
        "connected_tables": ["WBSApprovedBy"],
    },
    "ZHANADB_WBSAPPROVEDBY": {
        "purpose": "Stores WBS approvers.",
        "connected_tables": ["WBS"],
    },
    "ZHANADB_WBSTRAINSET": {
        "purpose": "WBS Train master data.",
        "connected_tables": ["PurchaseOrderSet"],
    },
}


# Common business words/synonyms users type for each table, used as a
# safety-net lookup when the planner's chosen table name does not exactly
# match the live schema (wrong case, missing ZHANADB_ prefix, a name copied
# from the descriptive "connected_tables" hints, etc.). Keyed by the exact,
# case-sensitive table name; values are lowercase synonyms.
TABLE_ALIASES = {
    "ZHANADB_PURCHASEORDERSET": [
        "po", "pos", "purchase order", "purchase orders", "order", "orders",
        "vendor", "vendors", "supplier", "suppliers",
    ],
    "ZHANADB_MATERIALSET": [
        "material", "materials", "item", "items", "product", "products",
        "commodity", "commodities", "goods",
    ],
    "ZHANADB_MATERIALFAMILYSET": [
        "material family", "material families", "material category",
        "material categories", "subfamily",
    ],
    "ZHANADB_INSPECTIONSET": [
        "inspection", "inspections", "qa", "quality check", "qc",
    ],
    "ZHANADB_INSPECTIONITEMSET": [
        "inspection item", "inspection items",
    ],
    "ZHANADB_NCRDCRDATASET": [
        "ncr", "dcr", "ncr/dcr", "non-conformance", "non conformance",
        "rejection", "rejections", "defect", "defects",
    ],
    "ZHANADB_NCRDCRITEMDATASET": ["ncr item", "dcr item"],
    "ZHANADB_QUERYLISTSET": [
        "query", "queries", "vendor query", "vendor queries",
    ],
    "ZHANADB_SERVICEORDERSET": [
        "service order", "service orders",
    ],
    "ZHANADB_CHANGENOTESET": [
        "change note", "change notes", "change request", "change requests",
    ],
    "ZHANADB_DOCUMENTSET": ["document", "documents", "attachment", "attachments"],
    "ZHANADB_COMMENTSET": ["comment", "comments", "remark", "remarks"],
    "ZHANADB_WBS": ["wbs", "work breakdown", "work breakdown structure"],
    "ZHANADB_PROJECTWBSSET": ["project wbs", "project", "projects"],
    "ZHANADB_POBGRELATIONSET": ["bank guarantee", "bank guarantees", "bg"],
    "ZHANADB_POASSIGNMENTSET": ["assignment", "assignments", "po assignment"],
    "ZHANADB_USERROLESET": ["role", "roles", "user role", "user roles"],
}
