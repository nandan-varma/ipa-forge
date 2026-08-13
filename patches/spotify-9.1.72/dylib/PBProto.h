// PBProto.h — minimal protobuf wire-format parse/edit for the Spotify
// bootstrap/customize rewrite. Generic tree model: no schema needed to walk,
// only to decide what to change (field numbers live in PremiumPatch.m).
//
// Wire format (proto3 subset): varint (0), 64-bit (1), length-delimited (2),
// 32-bit (5). Messages = repeated length-delimited fields of sub-messages.
#ifndef PBPROTO_H
#define PBPROTO_H

#import <Foundation/Foundation.h>

typedef NS_ENUM(int, PBWireType) { PBWireVarint = 0, PBWire64 = 1, PBWireLen = 2, PBWire32 = 5 };

@interface PBNode : NSObject
@property (nonatomic) int fieldNumber;
@property (nonatomic) PBWireType wireType;
@property (nonatomic) unsigned long long varintValue;       // varint/64/32
@property (nonatomic, strong) NSData *dataValue;            // length-delimited raw bytes
@property (nonatomic, strong) NSMutableArray<PBNode *> *children; // decoded sub-messages (PBWireLen decoded as message)
@end

@interface PBProto : NSObject

// Parse raw bytes into a tree. Length-delimited fields are decoded into
// child message nodes (attempting full nesting); raw bytes preserved for
// rebuild fidelity.
+ (NSMutableArray<PBNode *> *)parse:(NSData *)data;

// Rebuild bytes from a node tree.
+ (NSData *)serialize:(NSArray<PBNode *> *)nodes;

// --- navigation helpers (all operate on the top-level message fields) ----
+ (PBNode *)messageField:(NSArray<PBNode *> *)nodes field:(int)field;    // single message field
+ (NSMutableArray<PBNode *> *)repeatedField:(NSArray<PBNode *> *)nodes field:(int)field; // repeated messages
+ (NSString *)stringValue:(PBNode *)node;                                 // len-field string
+ (unsigned long long)varintValue:(PBNode *)node;                         // varint field
+ (BOOL)boolValue:(PBNode *)node;

// --- node constructors ----------------------------------------------------
+ (PBNode *)varintField:(int)field value:(unsigned long long)value;
+ (PBNode *)stringField:(int)field value:(NSString *)value;
+ (PBNode *)messageFieldBuilder:(int)field fields:(NSArray<PBNode *> *)fields;

// --- mutation helpers ----------------------------------------------------
// Replace (or add) a message sub-field inside `parent` with a freshly built
// message; `remove:YES` deletes any existing field with that number.
+ (void)setMessageField:(NSMutableArray<PBNode *> *)parent field:(int)field builder:(NSArray<PBNode *> * (^)(void))builder remove:(BOOL)remove;

// Replace (or add) a varint sub-field.
+ (void)setVarintField:(NSMutableArray<PBNode *> *)parent field:(int)field value:(unsigned long long)value;

// Replace (or add) a length-delimited string sub-field.
+ (void)setStringField:(NSMutableArray<PBNode *> *)parent field:(int)field value:(NSString *)value;

// Remove every field with `field` from `parent` (for repeated removals).
+ (void)removeField:(NSMutableArray<PBNode *> *)parent field:(int)field;

// Map entry = message{1: key(string), 2: value(message)}.
// Replaces the entry with matching key, or appends a new one.
+ (void)setMapEntry:(NSMutableArray<PBNode *> *)map key:(NSString *)key valueBuilder:(NSArray<PBNode *> * (^)(void))builder;
+ (void)removeMapEntry:(NSMutableArray<PBNode *> *)map key:(NSString *)key;

@end
#endif
