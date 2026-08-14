// PBProto.m — minimal protobuf wire-format parse/edit.
#import "PBProto.h"

@implementation PBNode
@end

@implementation PBProto

+ (NSMutableArray<PBNode *> *)parse:(NSData *)data {
    return [self parseFields:data range:NSMakeRange(0, data.length)];
}

// Parse consecutive fields from `range`; stops at end of range.
+ (NSMutableArray<PBNode *> *)parseFields:(NSData *)data range:(NSRange)range {
    NSMutableArray<PBNode *> *nodes = [NSMutableArray array];
    const uint8_t *bytes = data.bytes;
    NSUInteger pos = range.location;
    NSUInteger end = range.location + range.length;

    while (pos < end) {
        // tag = (fieldNumber << 3) | wireType (varint)
        unsigned long long tag = 0;
        int shift = 0;
        BOOL more = YES;
        while (more) {
            if (pos >= end) return nodes;
            uint8_t b = bytes[pos++];
            tag |= (unsigned long long)(b & 0x7F) << shift;
            shift += 7;
            more = (b & 0x80) != 0;
        }
        int field = (int)(tag >> 3);
        PBWireType wire = (PBWireType)(tag & 7);
        if (field == 0) break; // malformed; stop

        PBNode *node = [PBNode new];
        node.fieldNumber = field;
        node.wireType = wire;

        switch (wire) {
            case PBWireVarint: {
                unsigned long long value = 0;
                shift = 0;
                more = YES;
                while (more) {
                    if (pos >= end) return nodes;
                    uint8_t b = bytes[pos++];
                    value |= (unsigned long long)(b & 0x7F) << shift;
                    shift += 7;
                    more = (b & 0x80) != 0;
                }
                node.varintValue = value;
                break;
            }
            case PBWire64: {
                if (pos + 8 > end) return nodes;
                node.varintValue = 0;
                for (int i = 0; i < 8; i++) node.varintValue |= ((unsigned long long)bytes[pos + i]) << (8 * i);
                pos += 8;
                break;
            }
            case PBWire32: {
                if (pos + 4 > end) return nodes;
                node.varintValue = 0;
                for (int i = 0; i < 4; i++) node.varintValue |= ((unsigned long long)bytes[pos + i]) << (8 * i);
                pos += 4;
                break;
            }
            case PBWireLen: {
                unsigned long long len = 0;
                shift = 0;
                more = YES;
                while (more) {
                    if (pos >= end) return nodes;
                    uint8_t b = bytes[pos++];
                    len |= (unsigned long long)(b & 0x7F) << shift;
                    shift += 7;
                    more = (b & 0x80) != 0;
                }
                if (pos + len > end) len = end - pos;
                node.dataValue = [data subdataWithRange:NSMakeRange(pos, (NSUInteger)len)];
                // decode as a nested message (may legitimately fail on strings —
                // keep the raw bytes either way)
                node.children = [self parseFields:data range:NSMakeRange(pos, (NSUInteger)len)];
                pos += (NSUInteger)len;
                break;
            }
            default:
                return nodes; // unsupported wire type; stop
        }
        [nodes addObject:node];
    }
    return nodes;
}

+ (NSData *)serialize:(NSArray<PBNode *> *)nodes {
    NSMutableData *out = [NSMutableData data];
    for (PBNode *node in nodes) {
        [self appendTag:out field:node.fieldNumber wire:node.wireType];
        switch (node.wireType) {
            case PBWireVarint: [self appendVarint:out value:node.varintValue]; break;
            case PBWire64: {
                unsigned long long v = node.varintValue;
                for (int i = 0; i < 8; i++) { uint8_t b = (uint8_t)(v >> (8 * i)); [out appendBytes:&b length:1]; }
                break;
            }
            case PBWire32: {
                unsigned long long v = node.varintValue;
                for (int i = 0; i < 4; i++) { uint8_t b = (uint8_t)(v >> (8 * i)); [out appendBytes:&b length:1]; }
                break;
            }
            case PBWireLen: {
                NSData *payload = node.children.count
                    ? [self serialize:node.children]
                    : (node.dataValue ?: [NSData data]);
                [self appendVarint:out value:payload.length];
                [out appendData:payload];
                break;
            }
        }
    }
    return out;
}

+ (void)appendTag:(NSMutableData *)out field:(int)field wire:(PBWireType)wire {
    [self appendVarint:out value:((unsigned long long)field << 3) | wire];
}

+ (void)appendVarint:(NSMutableData *)out value:(unsigned long long)value {
    while (value >= 0x80) {
        uint8_t b = (uint8_t)(value & 0x7F) | 0x80;
        [out appendBytes:&b length:1];
        value >>= 7;
    }
    uint8_t b = (uint8_t)value;
    [out appendBytes:&b length:1];
}

// --- navigation ------------------------------------------------------------

+ (PBNode *)messageField:(NSArray<PBNode *> *)nodes field:(int)field {
    for (PBNode *n in nodes) if (n.fieldNumber == field && n.wireType == PBWireLen && n.children.count) return n;
    return nil;
}

+ (NSMutableArray<PBNode *> *)repeatedField:(NSArray<PBNode *> *)nodes field:(int)field {
    NSMutableArray *out = [NSMutableArray array];
    for (PBNode *n in nodes) if (n.fieldNumber == field && n.wireType == PBWireLen) [out addObject:n];
    return out;
}

+ (NSString *)stringValue:(PBNode *)node {
    NSData *d = node.dataValue;
    if (!d) return nil;
    return [[NSString alloc] initWithData:d encoding:NSUTF8StringEncoding];
}

+ (unsigned long long)varintValue:(PBNode *)node {
    return node.varintValue;
}

+ (BOOL)boolValue:(PBNode *)node {
    return node.varintValue != 0;
}

// --- mutation --------------------------------------------------------------

+ (void)setMessageField:(NSMutableArray<PBNode *> *)parent field:(int)field
                builder:(NSArray<PBNode *> * (^)(void))builder remove:(BOOL)remove {
    PBNode *existing = nil;
    for (PBNode *n in parent) if (n.fieldNumber == field) { existing = n; break; }
    if (existing) [parent removeObject:existing];
    if (remove) return;
    PBNode *node = [PBNode new];
    node.fieldNumber = field;
    node.wireType = PBWireLen;
    node.children = [builder() mutableCopy];
    [parent addObject:node];
}

+ (PBNode *)varintField:(int)field value:(unsigned long long)value {
    PBNode *n = [PBNode new];
    n.fieldNumber = field;
    n.wireType = PBWireVarint;
    n.varintValue = value;
    return n;
}

+ (PBNode *)stringField:(int)field value:(NSString *)value {
    PBNode *n = [PBNode new];
    n.fieldNumber = field;
    n.wireType = PBWireLen;
    n.dataValue = [value dataUsingEncoding:NSUTF8StringEncoding];
    return n;
}

+ (PBNode *)messageFieldBuilder:(int)field fields:(NSArray<PBNode *> *)fields {
    PBNode *n = [PBNode new];
    n.fieldNumber = field;
    n.wireType = PBWireLen;
    n.children = [fields mutableCopy];
    return n;
}

+ (void)setVarintField:(NSMutableArray<PBNode *> *)parent field:(int)field value:(unsigned long long)value {
    for (PBNode *n in parent) if (n.fieldNumber == field) { [parent removeObject:n]; break; }
    [parent addObject:[self varintField:field value:value]];
}

+ (void)setStringField:(NSMutableArray<PBNode *> *)parent field:(int)field value:(NSString *)value {
    for (PBNode *n in parent) if (n.fieldNumber == field) { [parent removeObject:n]; break; }
    [parent addObject:[self stringField:field value:value]];
}

+ (void)removeField:(NSMutableArray<PBNode *> *)parent field:(int)field {
    NSMutableIndexSet *remove = [NSMutableIndexSet indexSet];
    [parent enumerateObjectsUsingBlock:^(PBNode *n, NSUInteger idx, BOOL *stop) {
        if (n.fieldNumber == field) [remove addIndex:idx];
    }];
    [parent removeObjectsAtIndexes:remove];
}

+ (void)setMapEntry:(NSMutableArray<PBNode *> *)map key:(NSString *)key valueBuilder:(NSArray<PBNode *> * (^)(void))builder {
    // find entry with matching key: entry msg {1: key string}
    PBNode *existing = nil;
    for (PBNode *entry in map) {
        for (PBNode *sub in entry.children) {
            if (sub.fieldNumber == 1 && [[self stringValue:sub] isEqualToString:key]) { existing = entry; break; }
        }
        if (existing) break;
    }
    NSMutableArray *fields = [NSMutableArray array];
    [fields addObject:[self stringField:1 value:key]];
    PBNode *valueMsg = [PBNode new];
    valueMsg.fieldNumber = 2;
    valueMsg.wireType = PBWireLen;
    valueMsg.children = [builder() mutableCopy];
    [fields addObject:valueMsg];

    if (existing) {
        existing.children = fields;
    } else {
        PBNode *entry = [PBNode new];
        entry.fieldNumber = 1;
        entry.wireType = PBWireLen;
        entry.children = fields;
        [map addObject:entry];
    }
}

+ (void)removeMapEntry:(NSMutableArray<PBNode *> *)map key:(NSString *)key {
    NSMutableIndexSet *remove = [NSMutableIndexSet indexSet];
    [map enumerateObjectsUsingBlock:^(PBNode *entry, NSUInteger idx, BOOL *stop) {
        for (PBNode *sub in entry.children) {
            if (sub.fieldNumber == 1 && [[self stringValue:sub] isEqualToString:key]) { [remove addIndex:idx]; break; }
        }
    }];
    [map removeObjectsAtIndexes:remove];
}

@end
