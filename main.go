package goredis

import (
	"context"
	"encoding/json"
	"github.com/redis/go-redis/v9"
	"time"
)

type CachedDataNotFoundByKey struct {
	Key string
}

func (e *CachedDataNotFoundByKey) Error() string {
	return "cached data not found by key " + e.Key
}

type RedisHelper struct {
	Ctx         context.Context
	RedisClient *redis.Client
	Expiration  time.Duration
}

func (dataSource *RedisHelper) Get(
	keySufix string,
	key string,
	data interface{},
) error {
	keyRedis := key + "_" + keySufix
	cachedDataString, err := dataSource.RedisClient.
		Get(dataSource.Ctx, keyRedis).Result()

	if err != nil {
		if err == redis.Nil {
			return &CachedDataNotFoundByKey{Key: keyRedis}
		} else {
			return err
		}
	}

	if err := json.Unmarshal([]byte(cachedDataString), data); err != nil {
		return err
	}

	return nil
}

func (dataSource *RedisHelper) Set(
	keySufix string,
	key string,
	data interface{},
) error {
	keyRedis := key + "_" + keySufix
	cachedDataBytes, err := json.Marshal(data)

	if err != nil {
		return err
	}

	return dataSource.RedisClient.
		Set(dataSource.Ctx, keyRedis, cachedDataBytes, dataSource.Expiration).
		Err()
}

func (dataSource *RedisHelper) Remove(
	keySufix string,
	key string,
) error {
	keyRedis := key + "_" + keySufix
	return dataSource.RedisClient.Del(context.Background(), keyRedis).Err()
}
