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

func NewClient(
	host string,
	port string,
	databaseNumber int,
) (*redis.Client, error) {
	address := host + ":" + port

	options := &redis.Options{
		Addr: address,
		DB:   databaseNumber,
	}
	client := redis.NewClient(options)

	return client, nil
}

func (redisHelper *RedisHelper) Get(
	keySufix string,
	key string,
	data interface{},
) error {
	keyRedis := key + "_" + keySufix
	cachedDataString, err := redisHelper.RedisClient.
		Get(redisHelper.Ctx, keyRedis).Result()

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

func (redisHelper *RedisHelper) Set(
	keySufix string,
	key string,
	data interface{},
) error {
	keyRedis := key + "_" + keySufix
	cachedDataBytes, err := json.Marshal(data)

	if err != nil {
		return err
	}

	return redisHelper.RedisClient.
		Set(redisHelper.Ctx, keyRedis, cachedDataBytes, redisHelper.Expiration).
		Err()
}

func (redisHelper *RedisHelper) Remove(
	keySufix string,
	key string,
) error {
	keyRedis := key + "_" + keySufix
	return redisHelper.RedisClient.Del(context.Background(), keyRedis).Err()
}
