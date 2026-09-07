"""All model calls, including child agents/cache/reasoning; unknown is not zero."""


def nonnegative(value):
    return isinstance(value,int) and not isinstance(value,bool) and value>=0


def tokens(calls, complete):
    if not complete:
        return (None,None,None)
    seen={}; input_total=output_total=0
    for call in calls:
        key=call.get("call_id")
        if not isinstance(key,str) or not key or not all(nonnegative(call.get(k)) for k in ("input_tokens","output_tokens")):
            return (None,None,None)
        if key in seen:
            if seen[key]!=call:
                return (None,None,None)
            continue
        seen[key]=call
        input_total+=call["input_tokens"]
        output_total+=call["output_tokens"]
    return input_total,output_total,input_total+output_total


def tool_counts(trace):
    counts={"total":0,"search":0,"read":0,"retrieval":0,"expand":0}
    seen=set()
    for event in trace:
        if event.get("kind")!="tool_call":
            continue
        key=event.get("call_id")
        if not key:
            return None
        if key in seen:
            continue
        seen.add(key); counts["total"]+=1
        name=event.get("tool","").lower()
        if any(s in name for s in ("search","find","grep","glob")):
            counts["search"]+=1; counts["retrieval"]+=1
        elif "expand" in name:
            counts["expand"]+=1; counts["retrieval"]+=1
        elif "read" in name:
            counts["read"]+=1; counts["retrieval"]+=1
    return counts


def coherent_usage(value, prefix):
    values=[getattr(value,f"{prefix}_llm_{part}_tokens") for part in ("input","output","total")]
    return all(nonnegative(v) for v in values) and values[0]+values[1]==values[2]
