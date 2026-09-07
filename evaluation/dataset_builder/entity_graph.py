"""Candidate graph only. Explicit IDs join records; names/aliases never merge identities."""
from urllib.parse import quote
from .contracts import (PREFIXES, ENTITY_TYPES, BUILDER_RELATIONS, provenance, fingerprint)


def union(left,right):
    values={fingerprint(v):v for v in [*left,*right]}
    return list(values.values())


class EntityGraph:
    def __init__(self,profiles,documents):
        self.profiles=profiles; self.documents=set(documents)
        self.entities={}; self.relations={}; self.warnings=[]

    def canonical(self,typ,key):
        typ=self.profiles.entity_mapping.type_map.get(typ,typ)
        if typ not in ENTITY_TYPES: raise ValueError("unsupported candidate entity type: "+str(typ))
        namespace=self.profiles.entity_mapping.identity_namespace
        return PREFIXES[typ]+":"+quote(namespace+str(key),safe="-._~")

    def sources(self,row,origin):
        locations=row.get("source_locations") or []
        if not isinstance(locations,list) or any(not isinstance(loc,dict) for loc in locations):
            raise ValueError("source_locations must be a list of structural locator objects")
        locations=[dict(loc) for loc in locations]
        documents=row.get("source_documents") or []
        if isinstance(documents,str): documents=[documents]
        documents=[*documents,*[loc["document"] for loc in locations if loc.get("document")]]
        aliases=self.profiles.source.document_aliases
        documents=sorted({aliases.get(d,d) for d in documents})
        for loc in locations:
            if "document" in loc: loc["document"]=aliases.get(loc["document"],loc["document"])
            loc["plane"]="raw"
        if origin=="parser": locations.append({"plane":"parser",**row["parser_location"]})
        unknown=set(documents)-self.documents
        if unknown: self.warnings.append({"code":"unresolved_source_document","documents":sorted(unknown)})
        return documents,locations

    @staticmethod
    def merge(existing,incoming):
        if existing["candidate_origin"]!=incoming["candidate_origin"]: existing["candidate_origin"]="both"
        existing["parser_supported"]|=incoming["parser_supported"]
        for field in ("source_documents","source_locations","generation_method"):
            existing[field]=union(existing[field],incoming[field])

    def add_entities(self,rows,origin):
        for row in rows:
            typ=self.profiles.entity_mapping.type_map.get(row.get("type"),row.get("type"))
            name=row.get("name")
            if typ not in ENTITY_TYPES or not isinstance(name,str) or not name.strip():
                self.warnings.append({"code":"invalid_entity_mapping","location":row.get("parser_location",row.get("source_locations"))}); continue
            documents,locations=self.sources(row,origin)
            explicit=row.get("id") is not None and str(row["id"]).strip()!=""
            key=row["id"] if explicit else "occurrence-"+fingerprint([origin,locations,typ,name])[:24]
            cid=self.canonical(typ,key)
            aliases=row.get("aliases") or []
            if isinstance(aliases,str): aliases=[aliases]
            aliases=[v for v in aliases if isinstance(v,str) and v.strip()]
            candidate={"id":cid,"canonical_id":cid,"type":typ,"name":name,"aliases":aliases,
                       "identity_basis":"explicit_profile_id" if explicit else "distinct_occurrence",
                       "facets":row.get("facets") or {},"name_variants":[name],
                       **provenance(origin,documents,locations,"profile_"+origin+"_entity")}
            if cid in self.entities:
                existing=self.entities[cid]; self.merge(existing,candidate)
                existing["aliases"]=union(existing["aliases"],[name,*aliases])
                existing["name_variants"]=union(existing["name_variants"],[name])
                for facet,value in candidate["facets"].items():
                    previous=existing["facets"].get(facet)
                    if previous is not None and previous!=value:
                        existing.setdefault("conflicts",[]).append({"facet":facet,"values":[previous,value]})
                    else: existing["facets"][facet]=value
            else: self.entities[cid]=candidate

    def endpoint(self,value):
        if isinstance(value,dict) and value.get("id") is not None:
            try: cid=self.canonical(value.get("type"),value["id"])
            except ValueError: return None
        else: cid=value  # string endpoints must be exact candidate IDs, never names/aliases
        return cid if isinstance(cid,str) and cid in self.entities else None

    def add_relations(self,rows,origin):
        for row in rows:
            source=self.endpoint(row.get("source")); target=self.endpoint(row.get("target"))
            relation=self.profiles.relation_mapping.type_map.get(row.get("relation"),row.get("relation"))
            if not source or not target or relation not in BUILDER_RELATIONS:
                self.warnings.append({"code":"unresolved_relation","source":row.get("source"),"target":row.get("target"),
                                      "relation":relation,"location":row.get("parser_location",row.get("source_locations"))}); continue
            models={"logical_models","physical_models"}
            signatures={"supported_by":({"metrics"},models),"requires_metric":({"purposes"},{"metrics"}),
                        "requires_dimension":({"purposes"},{"dimensions"}),"belongs_to_object":(models,{"business_objects"}),
                        "implemented_by":({"logical_models"},{"physical_models"}),"upstream":(models,models),
                        "downstream":(models,models),"has_field":(models,{"fields"})}
            source_types,target_types=signatures[relation]
            if self.entities[source]["type"] not in source_types or self.entities[target]["type"] not in target_types:
                self.warnings.append({"code":"relation_type_mismatch","source":source,"relation":relation,"target":target}); continue
            documents,locations=self.sources(row,origin)
            key="relation-"+fingerprint([source,relation,target])[:24]
            candidate={"id":key,"source":source,"relation":relation,"target":target,
                       "structural_only":relation=="has_field",
                       **provenance(origin,documents,locations,"profile_"+origin+"_relation")}
            if origin=="raw_independent":
                candidate["raw_verified"]=True
                candidate["raw_verification_scope"]="configured raw relation rule matched; semantic approval still required"
            if key in self.relations:
                existing=self.relations[key]; self.merge(existing,candidate)
                existing["raw_verified"]|=candidate["raw_verified"]
                if candidate.get("raw_verification_scope"): existing["raw_verification_scope"]=candidate["raw_verification_scope"]
            else: self.relations[key]=candidate

    def outgoing(self,cid,relations):
        return [r for r in self.relations.values() if r["source"]==cid and r["relation"] in relations]
